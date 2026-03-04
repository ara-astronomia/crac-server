# Guida alla Revisione del Codice - crac-server (Branch 43-new-service)

Questa guida aggiornata include le criticità riscontrate nel nuovo branch relativo ai servizi geografici e dati immagine.

## 🔴 1. Pericolo Critico: Chiamate Async da Thread Sync
- **Problema:** `WeatherService._emergency_closure` viene eseguito in un `Thread` sincrono e chiama `ROOF.close()`. 
- **Dettaglio:** `ROOF.close()` è ora un metodo `async`. Chiamarlo senza `await` (impossibile in un thread sync senza loop) significa che **l'azione di chiusura del tetto non viene mai eseguita**.
- **Azione Urgente:** Convertire `_emergency_closure` in un task `asyncio` e usare `await ROOF.close()`.

## 2. Inconsistenza Async nei Nuovi Servizi
- **Problema:** `GeographicServicer` e `ImageConfigServicer` usano `def` invece di `async def`.
- **Azione:** Sincronizzare tutti i servicer gRPC sullo standard `async def` per evitare blocchi dell'event loop e garantire coerenza architetturale.

## 3. Polling e I/O Bloccante (Persistente)
- **Meteo:** `urllib.request.urlopen` è ancora presente in `Weather._get_sensor`. Questo blocca il server gRPC durante il recupero dei dati meteo. Sostituire con `httpx` asincrono.
- **Telescopio:** Il polling basato su thread con apertura/chiusura continua del socket rimane inefficiente. Migrare a un task `asyncio` con connessione persistente.

## 4. Robustezza Parsing (Geographic)
- **Problema:** Il parsing delle coordinate via Regex in `GeographicServicer` è fragile e prono a errori di sessagesimale.
- **Azione:** Spostare la logica di conversione in una utility testabile e aggiungere validazione robusta dei dati letti dal `config.ini`.

## 5. Gestione Risorse
- **Azione:** Con l'aumentare dei servizi, è fondamentale implementare un `cleanup` centralizzato in `app.py` che fermi tutti i polling (`TELESCOPE.polling_end()`, ecc.) in caso di `KeyboardInterrupt` o segnali di sistema.
