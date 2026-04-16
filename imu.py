from umqtt.simple import MQTTClient
from time import sleep
import network
import neopixel
import socket
import time
from machine import Pin
#ssid = "iliadbox-0E64B8"
#password = "f54rzq5nmbqbv9d3q764r7"
#ssid="IoT-UNICA"
#password="I@T_unic@2019"

ssid="iPhone di Michele"
password="ArchitetturaEdge"
#ssid ="Free WiFi Ca"
#password=""
ClientID = "raspberry-sub"
name ='prova'
ip_address='172.25.192.1'

server="broker.mqtt-dashboard.com"
topic = b'tinys3/imu'
msg ='near_miss'



# Configurazione WiFi e MQTT
myled =Pin(17,Pin.OUT)
myled.value(1)
ClientID = "mqtt-sensor-variance"
msg_template = "{},{},near_miss"
treshold = 2  
np = neopixel.NeoPixel(Pin(18), 1)
CSV_FILENAME="/dataset/Dataset_imu.csv"
# Imposta il LED 0 al colore verde
np[0] = (255, 0, 0) 
np.write()  # Aggiorna la striscia LED

# Connessione WiFi
def connect_wifi(ssid, password):
    sta_if = network.WLAN(network.STA_IF)
    sta_if.active(True)
    sta_if.connect(ssid, password)
    while not sta_if.isconnected():
        print("Connessione WiFi in corso...")
        time.sleep(1)
    print("Connesso al WiFi:", sta_if.ifconfig())
    np[0] = (0, 255, 0) 
    np.write()


def mqtt_callback(topic, msg):
    print("Messaggio ricevuto dal topic", topic.decode("utf-8"), ":", msg)
    
def process_dataset(mqtt_client, topic, treshold):
    imu_dataset = []
    count=0
    send_message=False
    # Leggi il file CSV
    np[0] = (0,0,255) 
    np.write()
    with open(CSV_FILENAME, 'r') as file:
        lines = file.readlines()
        
        # Intestazioni dalla prima riga
        headers = lines[0].strip().split(',') 
        
        # Processa ogni riga
        for line in lines[1:]:
            row = line.strip().split(',')
            timestamp = row[0]  # Il primo elemento è il timestamp
            if(count>=20):
                msg="end"
                mqtt_client.publish(topic, msg.encode('utf-8'), qos=0)
                print("Messaggio inviato: ",msg)
                break
            count+=1
    
            msg=row[1]+","+row[2]+","+row[3]+","+row[4]+","+row[5]+","+row[6]+","+row[7]+","+row[8]+","+row[9]+","+row[10]+","+row[11]+","+row[12]
            mqtt_client.publish(topic, msg.encode('utf-8'), qos=0)
            print("Messaggio inviato: ",msg)
                
            time.sleep(0.2)
def receive_full_request(client):
    request = b""
    while b"\r\n\r\n" not in request:
        request += client.recv(1024)

    headers, rest = request.split(b"\r\n\r\n", 1)
    headers_str = headers.decode()

    # Estrae la lunghezza del contenuto
    content_length = 0
    for line in headers_str.split("\r\n"):
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":")[1].strip())
            break

    
    body = rest
    while len(body) < content_length:
        body += client.recv(1024)

    return headers_str, body
def start_http_server_for_model():
    global http_server_socket
    addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
         
    http_server_socket = socket.socket()
    http_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    http_server_socket.bind(addr)
    http_server_socket.listen(1)
    # rimane bloccante per la configurazione iniziale
    print("Server HTTP in ascolto per ricezione modello...")
    cl, addr = http_server_socket.accept()
    print("Connessione da", addr)

    headers, body = receive_full_request(cl)

    if "POST /model" in headers:
        with open("model.py", "w") as f:
            f.write(body.decode())

        print("Modello salvato come model.py")

        response = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nModello ricevuto"
        cl.send(response.encode())
    else:
        response = "HTTP/1.1 400 Bad Request\r\nContent-Type: text/plain\r\n\r\nRichiesta non valida"
        cl.send(response.encode())

    cl.close()
    # Non viene chiuso il socket, lo riutilizziamo per gli interrupt

def import_model():
    import model
    return model


def setup_http_server():
    global http_server_socket
    # Riutilizza il socket già creato da start_http_server_for_model()
    http_server_socket.setblocking(False)  # Non-blocking
    print("Server HTTP configurato per interrupt...")

def handle_http_interrupt(model):
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

def continuous_inference(model):
    print("Inizio ciclo di inferenza continua...")

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
        # gestione interrupt
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
            # Nessuna connessione HTTP in arrivo 
            pass

        # inferenza
        if model and data_lines:
            line = data_lines[line_index % len(data_lines)]
            values = line.strip().split(",")
            row = dict(zip(header, values))

            try:
                features = [float(row[h]) for h in header[1:]]
                y_pred = model.score(features)
                print(f"Inferenza {line_index + 1}: Pred={y_pred}")
                line_index += 1
            except Exception as e:
                print("Errore durante inferenza:", e)

        time.sleep(1)

    

connect_wifi(ssid, password)
mqtt_client = MQTTClient(ClientID, server)
mqtt_client.set_callback(mqtt_callback)
mqtt_client.connect()
print("Connesso al broker MQTT")
subscribe_topic="tinys3/check"
mqtt_client.subscribe(subscribe_topic)

    
  
# Processa il dataset e invia i messaggi MQTT
process_dataset( mqtt_client, topic, treshold)
start_http_server_for_model()
model=import_model()
setup_http_server()
np[0] = (128, 128, 0) 
np.write()

continuous_inference(model)
mqtt_client.disconnect()
print("Disconnesso dal broker MQTT")
np[0] = (0, 0, 0) 
np.write()

