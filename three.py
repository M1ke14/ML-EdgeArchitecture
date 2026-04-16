import network
import time
from umqtt.simple import MQTTClient
import urequests
import socket
import select
import neopixel
from machine import Pin

WIFI_SSID = "iPhone di Michele"
WIFI_PASS = "ArchitetturaEdge"
MQTT_BROKER = "broker.mqtt-dashboard.com"
MQTT_TOPIC = b"tinys3/three"
#url da cambiare
UPLOAD_URL = "http://192.168.1.100:8000/upload"
EDGE_ID = "edge_three"
CSV_FILENAME = "/dataset/dataset_three.csv"

received_data = []
model = None
http_server_socket = None

myled =Pin(17,Pin.OUT)
myled.value(1)
leddata=18
num_leds=1
np =neopixel.NeoPixel(Pin(leddata),num_leds)
np[0] =(255,0,0)
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
    np[0]=(0,255,0)
    np.write()
# Legge CSV e invia dati via MQTT 
def send_data_from_csv(client):
    count=0
    np[0]=(0,0,255)
    np.write()
    try:
        with open(CSV_FILENAME, "r") as f:
            lines = f.readlines()
        for line in lines[1:]:  # Salta intestazione
            if(count>=20):
                msg="end"
                client.publish(MQTT_TOPIC, msg)
                print("Inviato MQTT:", msg)
                break
            parts = line.strip().split(",")
            if len(parts) != 3:
                print("Riga malformata:", line)
                continue
            timestamp, device, rssi = parts
            label = 1 if int(rssi) > -75 else 0
            msg = f"{timestamp},{device},{rssi},{label}"
            client.publish(MQTT_TOPIC, msg)
            print("Inviato MQTT:", msg)
            received_data.append({
                "timestamp": timestamp,
                "device": device,
                "rssi": rssi,
                "label": label
            })
            time.sleep(0.2)
            count+=1
    except Exception as e:
        print("Errore lettura/invio da CSV:", e)
def receive_full_request(client):
    request = b""
    while b"\r\n\r\n" not in request:
        request += client.recv(1024)

    headers, rest = request.split(b"\r\n\r\n", 1)
    headers_str = headers.decode()

    # Estrai la lunghezza del contenuto
    content_length = 0
    for line in headers_str.split("\r\n"):
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":")[1].strip())
            print(content_length)
            break

    # Leggi il corpo intero
    body = rest
    while len(body) < content_length:
        body += client.recv(1024)

    return headers_str, body
# Ricezione modello via HTTP 
def start_http_server_for_model():
    global http_server_socket
    addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
         
    http_server_socket = socket.socket()
    http_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    http_server_socket.bind(addr)
    http_server_socket.listen(1)
    # Mantieni bloccante per la configurazione iniziale
    print("Server HTTP in ascolto per ricezione modello...")
    
    cl, addr = http_server_socket.accept()
    print("Connessione da", addr)

    headers, body = receive_full_request(cl)

    if "POST /model" in headers:
       with open("model.py", "wb") as f:
        f.write(body)

        print("Modello salvato come model.py")

        response = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nModello ricevuto"
        cl.send(response.encode())
    else:
        response = "HTTP/1.1 400 Bad Request\r\nContent-Type: text/plain\r\n\r\nRichiesta non valida"
        cl.send(response.encode())

    cl.close()
            
    # Non chiudiamo il socket, lo riutilizziamo per gli interrupt

def import_model():
    import model
    return model


# socket non bloccante
def setup_http_server():
    global http_server_socket
    # Riutilizza il socket già creato da start_http_server_for_model()
    http_server_socket.setblocking(False)  # Non-blocking
    print("Server HTTP configurato per interrupt...")

def handle_http_interrupt():
    global model
    try:
        cl, addr = http_server_socket.accept()
        print("Interrupt HTTP ricevuto da", addr)
        request = cl.recv(2048)
        request_str = request.decode()
        
        if "POST /model" in request_str:
            body_start = request_str.find("\r\n\r\n") + 4
            model_code = request_str[body_start:]
            with open("model.py", "w") as f:
                f.write(model_code)
            print("Nuovo modello salvato, ricaricando...")
            
            # Ricarica il modello
            import sys
            if 'model' in sys.modules:
                del sys.modules['model']
            model = import_model()
            
            response = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nModello aggiornato"
        else:
            response = "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\n\r\nEndpoint non trovato"
        
        cl.send(response)
        cl.close()
        print("Interrupt completato, ritorno al ciclo di inferenza")
        
    except OSError:
        # Nessuna connessione in arrivo
        pass

def continuous_inference():
    global model
    print("Inizio ciclo di inferenza continua...")
    
    # Carica i dati del CSV una volta
    try:
        with open(CSV_FILENAME, 'r') as f:
            lines = f.readlines()
            header = lines[0].strip().split(",")
            data_lines = lines[1:]
    except Exception as e:
        print("Errore caricamento CSV:", e)
        return
    
    line_index = 0
    
    while True:
        # Controlla se c'è una richiesta HTTP in arrivo
        try:
            ready = select.select([http_server_socket], [], [], 0)  # Timeout 0 = non-blocking
            if ready[0]:
                handle_http_interrupt()
        except:
            pass
        
        # Esegui inferenza su una riga
        if model and data_lines:
            line = data_lines[line_index % len(data_lines)]
            values = line.strip().split(",")
            row = dict(zip(header, values))
            
            try:
                rssi = float(row["rssi"])
                X = [rssi]
                y_true = 1 if rssi > -75 else 0
                y_pred = model.score(X)
                print(f"Inferenza {line_index + 1}: RSSI={rssi}, GT={y_true}, Pred={y_pred}")
                line_index += 1
            except Exception as e:
                print("Errore durante inferenza:", e)
        
        time.sleep(1)  # Pausa tra le inferenze


def main():
    global model
    
    connect_wifi()
    mqtt_client = MQTTClient(EDGE_ID, MQTT_BROKER)
    mqtt_client.connect()
    send_data_from_csv(mqtt_client)
    
    # Setup iniziale del modello
    start_http_server_for_model()
    model = import_model()
    
    
    mqtt_client.disconnect()
    
    # Setup server HTTP per interrupt
    setup_http_server()
    np[0]=(128,128,0)
    np.write()
    # Inizia il ciclo di inferenza continua con gestione interrupt
    continuous_inference()

main()
