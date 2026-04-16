import network
import time
from umqtt.simple import MQTTClient
import urequests
import socket
import select
import neopixel
from machine import Pin
import sys
import gc


WIFI_SSID = "iPhone di Michele"
WIFI_PASS = "ArchitetturaEdge"
MQTT_BROKER = "broker.mqtt-dashboard.com"
MQTT_TOPIC_THREE = b"tinys3/three"
MQTT_TOPIC_IMU = b"tinys3/imu"

# URL da cambiare
UPLOAD_URL = "http://192.168.1.100:8000/upload"
EDGE_ID = "edge_three"
CSV_FILENAME_THREE = "/dataset/dataset_three.csv"
CSV_FILENAME_IMU = "/dataset/Dataset_imu.csv"

# Variabili globali
received_data = []
models = [None, None]
http_server_socket = None
mqtt_client = None

# Setup LED
myled = Pin(17, Pin.OUT)
myled.value(1)
leddata = 18
num_leds = 1
np = neopixel.NeoPixel(Pin(leddata), num_leds)
np[0] = (255, 0, 0)
np.write()

# WiFi Connection
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASS)
    while not wlan.isconnected():
        print("Connessione WiFi in corso...")
        time.sleep(1)
    print("Connesso al WiFi:", wlan.ifconfig())
    np[0] = (0, 255, 0)
    np.write()

# Funzione per importare modello da file
def import_model_from_file(filename):
    try:
        # Rimuovi estensione .py per l'import
        module_name = filename.replace('.py', '').replace('/', '.')
        
        # Se il modulo è già caricato viene rimosso
        if module_name in sys.modules:
            del sys.modules[module_name]
        
        # Importa il modulo
        module = __import__(module_name)
        print(f"Modello {filename} importato correttamente")
        return module
    except Exception as e:
        print(f"Errore importando {filename}: {e}")
        return None

# Legge CSV e invia dati via MQTT 
def send_data_from_csv(client):
    global received_data
    count = 0
    np[0] = (0, 0, 255)
    np.write()
    
    # Invio dati THREE
    try:
        with open(CSV_FILENAME_THREE, "r") as f:
            lines = f.readlines()
        
        for line in lines[1:]:  # Salta intestazione
            if count >= 2:
                msg = "end"
                client.publish(MQTT_TOPIC_THREE, msg)
                print("Inviato MQTT THREE:", msg)
                break
            
            parts = line.strip().split(",")
            if len(parts) != 3:
                print("Riga malformata:", line)
                continue
            
            timestamp, device, rssi = parts
            label = 1 if int(rssi) > -75 else 0
            msg = f"{timestamp},{device},{rssi},{label}"
            client.publish(MQTT_TOPIC_THREE, msg)
            print("Inviato MQTT THREE:", msg)
            
            received_data.append({
                "timestamp": timestamp,
                "device": device,
                "rssi": rssi,
                "label": label
            })
            count += 1
            time.sleep(0.2)
    
    except Exception as e:
        print("Errore leggendo CSV THREE:", e)
    
    # Reset counter per IMU
    count = 0
    
    # Invio dati IMU
    try:
        with open(CSV_FILENAME_IMU, 'r') as file:
            lines = file.readlines()
        
        # Intestazioni dalla prima riga
        headers = lines[0].strip().split(',')
        
        # Processa ogni riga
        for line in lines[1:]:
            if count >= 1:
                msg = "end"
                client.publish(MQTT_TOPIC_IMU, msg.encode('utf-8'), qos=0)
                print("Messaggio IMU inviato:", msg)
                break
            
            row = line.strip().split(',')
            if len(row) < 13:
                print("Riga IMU malformata:", line)
                continue
            
            # Costruisci messaggio con i dati IMU 
            msg = ",".join(row[1:13])
            client.publish(MQTT_TOPIC_IMU, msg.encode('utf-8'), qos=0)
            print("Messaggio IMU inviato:", msg)
            
            count += 1
            time.sleep(0.2)
    
    except Exception as e:
        print("Errore leggendo CSV IMU:", e)

def receive_full_request(client):
    request = b""
    try:
        while b"\r\n\r\n" not in request:
            chunk = client.recv(1024)
            if not chunk:
                break
            request += chunk

        if b"\r\n\r\n" not in request:
            return "", b""

        headers, rest = request.split(b"\r\n\r\n", 1)
        headers_str = headers.decode()

        # Estrai la lunghezza del contenuto
        content_length = 0
        for line in headers_str.split("\r\n"):
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":")[1].strip())
                break

        # Leggi il corpo intero
        body = rest
        while len(body) < content_length:
            chunk = client.recv(1024)
            if not chunk:
                break
            body += chunk

        return headers_str, body
    except Exception as e:
        print("Errore ricevendo richiesta:", e)
        return "", b""

# Ricezione modello via HTTP 
def start_http_server_for_model():
    global http_server_socket
    
    try:
        addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
        http_server_socket = socket.socket()
        http_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        http_server_socket.bind(addr)
        http_server_socket.listen(1)
        
        print("In attesa di 2 modelli via HTTP...")

        for i in range(2):
            try:
                cl, addr = http_server_socket.accept()
                print(f"Connessione {i+1} da", addr)
                headers, body = receive_full_request(cl)

                if "POST /model" in headers:
                    model_filename = f"model{i+1}.py"
                    with open(model_filename, "w") as f:
                        f.write(body.decode())

                    print(f"Modello {i+1} salvato come {model_filename}")
                    response = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nModello ricevuto"
                    cl.send(response.encode())
                else:
                    response = "HTTP/1.1 400 Bad Request\r\nContent-Type: text/plain\r\n\r\nRichiesta non valida"
                    cl.send(response.encode())

                cl.close()
            except Exception as e:
                print(f"Errore ricevendo modello {i+1}: {e}")
                
    except Exception as e:
        print("Errore setup server HTTP:", e)

def import_models():
    global models
    models = [
        import_model_from_file("model1.py"),
        import_model_from_file("model2.py")
    ]
    print("Modelli importati:", [m is not None for m in models])

# Gestione interrupt HTTP
def setup_http_server():
    global http_server_socket
    if http_server_socket:
        try:
            http_server_socket.setblocking(False)
            print("Server HTTP configurato per interrupt...")
        except Exception as e:
            print("Errore configurando server HTTP:", e)

def handle_http_interrupt():
    global models
    try:
        cl, addr = http_server_socket.accept()
        print("Interrupt HTTP ricevuto da", addr)
        
        headers, body = receive_full_request(cl)
        
        if "POST /model" in headers:
            # Determina quale modello aggiornare
            model_index = 0  # Default primo modello
            if "model2" in headers:
                model_index = 1
            
            model_filename = f"model{model_index + 1}.py"
            with open(model_filename, "w") as f:
                f.write(body.decode())
            print(f"Nuovo modello {model_index + 1} salvato, ricaricando...")
            
            # Ricarica il modello specifico
            models[model_index] = import_model_from_file(model_filename)
            
            response = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nModello aggiornato"
        else:
            response = "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\n\r\nEndpoint non trovato"
        
        cl.send(response.encode())
        cl.close()
        print("Interrupt completato, ritorno al ciclo di inferenza")
        
    except OSError:
        # Nessuna connessione in arrivo
        pass
    except Exception as e:
        print("Errore handling interrupt:", e)

def continuous_inference():
    global models
    print("Inizio ciclo di inferenza continua...")
    
    # Carica i dati del CSV THREE una volta
    data_lines_three = []
    header_three = []
    try:
        with open(CSV_FILENAME_THREE, 'r') as f:
            lines = f.readlines()
            header_three = lines[0].strip().split(",")
            data_lines_three = lines[1:]
    except Exception as e:
        print("Errore caricamento CSV THREE:", e)
    
    # Carica i dati del CSV IMU una volta
    data_lines_imu = []
    header_imu = []
    try:
        with open(CSV_FILENAME_IMU, 'r') as f:
            lines = f.readlines()
            header_imu = lines[0].strip().split(",")
            data_lines_imu = lines[1:]
    except Exception as e:
        print("Errore caricamento CSV IMU:", e)
    
    line_index = 0
    
    while True:
        # Controlla se c'è una richiesta HTTP in arrivo
        try:
            if http_server_socket:
                ready = select.select([http_server_socket], [], [], 0)
                if ready[0]:
                    handle_http_interrupt()
        except Exception as e:
            print("Errore controllo interrupt:", e)
        
        # Esegui inferenza sui dati THREE
        if models[0] and data_lines_three:
            line = data_lines_three[line_index % len(data_lines_three)]
            values = line.strip().split(",")
            
            if len(values) >= 3:
                try:
                    rssi = float(values[2])  # Colonna RSSI
                    y_true = 1 if rssi > -75 else 0
                    
                    # Assumiamo che il modello abbia un metodo predict o score
                    if hasattr(models[0], 'predict'):
                        y_pred = models[0].predict([rssi])
                    elif hasattr(models[0], 'score'):
                        y_pred = models[0].score([rssi])
                    else:
                        y_pred = "N/A"
                    
                    print(f"Inferenza THREE {line_index + 1}: RSSI={rssi}, GT={y_true}, Pred={y_pred}")
                except Exception as e:
                    print("Errore durante inferenza THREE:", e)
        
        # Esegui inferenza sui dati IMU
        if models[1] and data_lines_imu:
            line = data_lines_imu[line_index % len(data_lines_imu)]
            values = line.strip().split(",")
            
            if len(values) >= 13:
                try:
                    # Usa le features IMU (escludendo timestamp)
                    features = [float(v) for v in values[1:13]]
                    
                    if hasattr(models[1], 'predict'):
                        y_pred = models[1].predict(features)
                    elif hasattr(models[1], 'score'):
                        y_pred = models[1].score(features)
                    else:
                        y_pred = "N/A"
                    
                    print(f"Inferenza IMU {line_index + 1}: Pred={y_pred}")
                except Exception as e:
                    print("Errore durante inferenza IMU:", e)
        
        line_index += 1
        time.sleep(0.3)  # Pausa tra le inferenze
        
        # Garbage collection periodico
        if line_index % 10 == 0:
            gc.collect()

def main():
    global mqtt_client
    
    try:
        connect_wifi()
        mqtt_client = MQTTClient(EDGE_ID, MQTT_BROKER)
        mqtt_client.connect()
        send_data_from_csv(mqtt_client)
        mqtt_client.disconnect()
        
        # Setup iniziale del modello
        start_http_server_for_model()
        import_models()
        
        # Setup server HTTP per interrupt
        setup_http_server()
        np[0] = (128, 128, 0)
        np.write()
        
        # Inizia il ciclo di inferenza continua con gestione interrupt
        continuous_inference()
        
    except Exception as e:
        print("Errore nel main:", e)
        np[0] = (255, 0, 0)  # LED rosso per errore
        np.write()
    finally:
        if mqtt_client:
            try:
                mqtt_client.disconnect()
            except:
                pass
        if http_server_socket:
            try:
                http_server_socket.close()
            except:
                pass

if __name__ == "__main__":
    main()
