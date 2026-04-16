import network
import time
from umqtt.simple import MQTTClient
import urequests
import neopixel
from machine import Pin

# Configurazione
WIFI_SSID = "iPhone di Michele"
WIFI_PASS = "ArchitetturaEdge"
MQTT_BROKER = "broker.mqtt-dashboard.com"
MQTT_TOPIC_DATA = b"tinys3/three"
MODEL_URL_THREE = "http://172.20.10.2:8000/model/edge_three"
UPLOAD_URL_THREE = "http://172.20.10.2:8000/upload/edge_three"
MODEL_URL_IMU = "http://172.20.10.2:8000/model/edge_imu"
UPLOAD_URL_IMU = "http://172.20.10.2:8000/upload/edge_imu"

ClientID = "fog-node"
EDGE_ID = "edge_three"
EDGE_IP_THREE = "http://172.20.10.9/model"
EDGE_IP_IMU ="http://172.20.10.12/model"

# Dati ricevuti
received_data_three = []
received_data_imu = []

done_three = False
done_imu = False

myled =Pin(17,Pin.OUT)
myled.value(1)
leddata=18
num_leds=1
np =neopixel.NeoPixel(Pin(leddata),num_leds)
np[0] =(255,0,0)
np.write()

# Connesione wifi
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


def mqtt_callback(topic, msg):
    global done_three, done_imu

    message = msg.decode()
    print("Ricevuto:", message)
    print("Topic:", topic)

    # Se ricevo messaggio "end", aggiorno la flag
    if message == "end":
        if topic == b"tinys3/three":
            done_three = True
            print("Fine ricezione da three")
        else:
            done_imu = True
            print("Fine ricezione da imu")
        return

    parts = message.split(",")

    if topic == b"tinys3/three":
        timestamp, device_id, rssi, label = parts
        received_data_three.append({
            "timestamp": timestamp,
            "device": device_id,
            "rssi": rssi,
            "label": label
        })
    else:
        AccX, AccY, AccZ, GyroX, GyroY, GyroZ, AngX, AngY, AngZ, MagX, MagY, MagZ = parts
        received_data_imu.append({
            "AccX": AccX,
            "AccY": AccY,
            "AccZ": AccZ,
            "GyroX": GyroX,
            "GyroY": GyroY,
            "GyroZ": GyroZ,
            "AngX": AngX,
            "AngY": AngY,
            "AngZ": AngZ,
            "MagX": MagX,
            "MagY": MagY,
            "MagZ": MagZ,
        })


# Invio all'host
def three_to_host():
        csv_data = "rssi\n" + "\n".join([str(record["rssi"]) for record in received_data_three])
        if(csv_data is not None):
            res = urequests.post(UPLOAD_URL_THREE, data=csv_data, headers={"Content-Type": "text/plain"})
            print(f"[{EDGE_ID}] Risposta Host:", res.text)
 
def imu_to_host():
    headers = ["AccX", "AccY", "AccZ",
                   "GyroX", "GyroY", "GyroZ",
                   "AngX", "AngY", "AngZ",
                   "MagX", "MagY", "MagZ"]
        
        # Crea la stringa CSV
    csv_data = ",".join(headers) + "\n"
    for row in received_data_imu:
        values = [str(row[h]) for h in headers]
        csv_data += ",".join(values) + "\n"
    if(csv_data is not None):
        res = urequests.post(UPLOAD_URL_IMU, data=csv_data, headers={"Content-Type": "text/plain"})
# Scarica modello
import urequests

def download_model():
    
    models = {
        "three": None,
        "imu": None
    }

    print("Attesa del modello...")
    np[0]=(128,128,0)
    np.write()
    while models["three"] is None or models["imu"] is None:
        if models["three"] is None:
            try:
                res = urequests.get(MODEL_URL_THREE)
                if res.status_code == 200:
                    print("Modello per three ricevuto.")
                    models["three"] = res.text
                    print(res.text)

                    print("Dimensione del modello:", len(models["three"]))
                res.close()
            except Exception as e:
                print(f"Errore nel download di three: {e}")

        if models["imu"] is None:
            try:
                res = urequests.get(MODEL_URL_IMU)
                if res.status_code == 200:
                    print("Modello per imu ricevuto.")
                    models["imu"] = res.text
                    print(res.text)
                    print("Dimensione del modello:", len(models["imu"]))
                res.close()
            except Exception as e:
                print(f"Errore nel download di imu: {e}")

    return models


   

# Invia modelli all'edge
def send_models_to_edge(models):
    tentativi = 0
    
    # --- Invio modello THREE ---
    model_data_three = models["three"]
    headers_three = {
        'Content-Type': 'text/plain',
        'Content-Length': str(len(model_data_three.encode()))
    }
    res = urequests.post(EDGE_IP_THREE, data=model_data_three, headers=headers_three)
    if res.status_code == 200:
        print("Modello 'three' inviato correttamente all'edge.")
    else:
        print("Errore HTTP (three):", res.status_code, res.text)
    res.close()

    # --- Invio modello IMU ---
    model_data_imu = models["imu"]
    headers_imu = {
        'Content-Type': 'text/plain',
        'Content-Length': str(len(model_data_imu.encode()))
    }
    res = urequests.post(EDGE_IP_IMU, data=model_data_imu, headers=headers_imu)
    if res.status_code == 200:
        print("Modello 'imu' inviato correttamente all'edge.")
    else:
        print("Errore HTTP (imu):", res.status_code, res.text)
    res.close()

    

def main():
    models = {
        "three": None,
        "imu": None
    }
    connect_wifi()
    mqtt_client = MQTTClient(ClientID, MQTT_BROKER)
    mqtt_client.set_callback(mqtt_callback)
    mqtt_client.connect()
    mqtt_client.subscribe(MQTT_TOPIC_DATA)
    mqtt_client.subscribe(b"tinys3/imu")

    print("Fog in ascolto MQTT...")
    
    np[0]=(0,0,255)
    np.write()
    while done_three is False or done_imu is False:
        mqtt_client.check_msg()
        time.sleep(0.2)
    
    print("Ricezione dati completata. Invio all'host...")
    three_to_host()
    imu_to_host()
    models = download_model()
    
    send_models_to_edge(models)

    mqtt_client.disconnect()
    print("Completato.")

main()

