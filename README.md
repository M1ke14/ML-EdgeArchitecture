# Distributed Edge ML Architecture: Integrazione di Machine Learning in Sistemi IoT

## Descrizione del Progetto
Questa evoluzione del framework IoT implementa una pipeline completa per il training, la distribuzione e l'inferenza di modelli di Machine Learning su microcontrollori a risorse limitate. Il sistema estende l'architettura Edge-Fog-Cloud introducendo la capacità di aggiornare i modelli di rilevamento anomalie (basati su OneClassSVM) in tempo reale senza la necessità di ri-flashare il firmware dei dispositivi.

## Architettura e Flusso Dati
L'architettura gestisce un ciclo di vita del modello chiuso (Closed-loop ML):

1.  **Livello Cloud (Server)**:
    - Utilizza un server Flask per addestrare modelli di rilevamento anomalie (OneClassSVM) su dataset IMU e RSSI.
    - Converte i modelli in codice Python puro utilizzando `m2cgen` per garantirne la compatibilità con l'interprete MicroPython.
    - Espone endpoint API per il download dei modelli aggiornati.

2.  **Livello Fog (Gateway)**:
    - Agisce come orchestratore tra il Cloud e l'Edge.
    - Scarica i nuovi modelli dal server e li distribuisce ai nodi Edge tramite richieste HTTP POST.
    - Continua a gestire l'aggregazione dei dati MQTT e il loro upload verso il cloud.

3.  **Livello Edge (Inferenza e Multitasking)**:
    - I nodi TinyS3 ricevono i modelli dal livello Fog e li salvano localmente.
    - Eseguono l'inferenza in tempo reale sui segnali acquisiti per classificare eventi critici.
    - Implementazione di multitasking per l'esecuzione parallela di più modelli di inferenza o task concorrenti sul singolo microcontrollore.

## Caratteristiche Tecniche e Ottimizzazione
- **Machine Learning**: Utilizzo di `m2cgen` per l'inferenza , minimizzando l'occupazione di memoria RAM.
- **Efficienza Energetica**: Test di durata della batteria (4 ore di operatività continua) con analisi del voltaggio residuo e stime di autonomia per scenari di inferenza singola e parallela.
- **Comunicazione**: Protocollo MQTT per i dati di telemetria e HTTP per la distribuzione dei modelli pesanti.

## Requisiti

### Hardware
- 3x Microcontrollori TinyS3 (ESP32-S3).
- Batteria LiPo per test di mobilità.

### Software
- **Server**: Python 3.x con Flask, Scikit-learn e `m2cgen`.
- **Edge/Fog**: MicroPython con librerie `umqtt.simple`, `urequests` e `ujson`.

## Installazione e Setup

1.  **Clone del repository**:
    ```bash
    git clone [https://github.com/m1ke14/ML-EdgeArchitecture.git](https://github.com/m1ke14/ML-EdgeArchitecture.git)
    ```
2.  **Avvio del Server Cloud**:
    Eseguire il notebook `Server_iot.ipynb` per avviare il servizio di training e l'API dei modelli.
3.  **Configurazione Nodi**:
    Aggiornare gli indirizzi IP del server e del gateway Fog nei file `fog.py` e `test_parallelo.py`.
4.  **Deployment**:
    - Caricare `fog.py` sul dispositivo Fog.
    - Caricare `test_parallelo.py` e i dataset CSV sui dispositivi Edge per avviare l'inferenza continua.

## Analisi delle Performance
Il sistema è stato validato tramite test di scarica della batteria, dimostrando un'autonomia stimata tra le 7 e le 9 ore a seconda della complessità computazionale (inferenza parallela vs singola) e della frequenza di invio dati.
