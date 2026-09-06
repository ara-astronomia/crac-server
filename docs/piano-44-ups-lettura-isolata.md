# Piano — Storia #44: isolare il fallimento di lettura di un singolo UPS

Issue: https://github.com/ara-astronomia/crac-server/issues/44
Milestone: "1. Sicurezza e affidabilità" (label `bug`, `safety`)
Branch: `fix/44-ups-read-isolation` (creato da `main` aggiornato)

## 1. Cosa dice l'issue oltre a quello che si vede dal codice

Bug puntuale: `UpsService.GetStatus` (crac_server/service/ups_service.py:32-58) itera
`ups_list` e chiama `UPS.status_for(device)` senza try/except. Il driver NUT
(`crac_server/component/ups/nut/ups.py:25-27`) trasforma qualsiasi eccezione di
connessione in un `ConnectionError` — che oggi si propaga fuori dal ciclo `for`,
facendo fallire *l'intera* risposta gRPC anche se l'altro UPS è raggiungibile.

L'issue fornisce uno pseudo-codice di riferimento (try/except per device, flag
`is_online`, skip dei chart per il device fallito) ma non è codice da copiare
com'è: usa `print(...)` invece del logger del progetto e non aggiorna
`calculate_status` per il caso "tutti i device falliscono". Non ci sono altri
dettagli nell'issue non deducibili dal codice (nessun formato di response
nuovo, nessun vincolo di sicurezza aggiuntivo).

## 2. Ambiente scelto

Fix Python puro in crac-server, nessuna dipendenza da Docker/INDIGO. Uso il
venv già presente in `../crac-server/.venv` con `uv run pytest`. Non serve lo
stack `crac-test-stack` per implementare né per validare via unit test.

## 3. Verifiche di config eseguite

- `ups_list` (config.ini / env) è una lista comma-separated arbitraria, già
  gestita in modo generico dal `for` esistente — nessuna modifica di config
  necessaria.
- Nello stack di test (`crac-test-stack/docker-compose.yml:41`),
  `UPS_DRIVER=simulator` seleziona `crac_server/component/ups/simulator/ups.py`,
  che legge sempre da `ups.ini` con fallback e **non solleva mai eccezioni**:
  non c'è modo di simulare un UPS irraggiungibile end-to-end nello stack senza
  modificare anche il simulatore. Fuori scope per questa issue → strategia di
  verifica spostata su unit test con mock (vedi punto 6).
- `crac-protobuf` è consumato da crac-server come `@main` (non pinnato a tag).
  Diff di `interfaces/ups.proto` tra `main` e il branch locale (`cover-mirror`):
  nessuna differenza → schema invariato, nessuna modifica proto richiesta.

## 4. Prerequisiti e riuso

- Pattern di isolamento del fallimento già presente in
  `crac_server/service/weather_service.py` (mock in
  `tests/service/test_weather_service.py::test_retriever_raise_exception`):
  un'eccezione durante il retrieve porta a `..._STATUS_UNSPECIFIED` invece di
  propagare. Stesso principio da applicare qui, per singolo device invece che
  per l'intero servizio.
- Nessuna nuova dipendenza esterna: `try/except (ConnectionError, Exception)`
  per device, `logger.error` (non `print`) per il fallimento, skip dei due
  chart (batteria/tensione) e di `response.devices.append(device)` per il
  device fallito.
- `calculate_status` va lasciato invariato: se tutti i device falliscono,
  `charts` resta vuoto e lo status resta `UPS_STATUS_UNSPECIFIED`, coerente
  col comportamento già esistente in `weather_service` per il fallimento
  totale.

## 5. Altri servizi coinvolti — verificati, nessuna modifica necessaria

- **crac-protobuf**: schema invariato (vedi punto 3), il campo `devices` già
  elenca solo i device che rispondono, non serve un campo esplicito
  "unavailable".
- **crac-cloud**: `ups.js::updateUpsUI` indicizza i chart per `urn`
  (`ups.<device>.chart.battery|voltage`) tramite una mappa e
  `_updateElement` fa `if (!chart) return;` — se il device fallito non produce
  chart, l'elemento UI semplicemente non viene aggiornato (resta l'ultimo
  valore noto) invece di andare in errore. `ups_cloud.py` non assume un numero
  fisso di device/chart. Nessuna modifica richiesta per il bug fix; un
  eventuale indicatore esplicito "UPS offline" in UI sarebbe una feature a
  parte, fuori dallo scope di questa issue.
- **crac-test-stack**: nessuna modifica al `docker-compose.yml`. Aggiunto però
  un flag `fail = true` per device in `ups.ini` del simulatore (vedi punto 6),
  che rende possibile la verifica manuale end-to-end nello stack senza
  toccare hardware reale — ripensato rispetto alla valutazione iniziale.

## 6. Strategia di test

Nessuna suite esistente per `ups_service` (`tests/service/` ha solo
`test_weather_service.py`). Aggiungo `tests/service/test_ups_service.py` sullo
stesso pattern (mock di `UPS` con `unittest.mock`), casi:

1. Tutti i device rispondono → 2 device in `response.devices`, 4 chart, status
   coerente con i valori.
2. Un device solleva `ConnectionError` → l'altro device è comunque presente in
   `response.devices` e nei chart (isolamento verificato).
3. Un device solleva un'`Exception` generica non-connessione → stesso
   isolamento (copre il branch "errore inatteso" dell'issue).
4. Tutti i device falliscono → `response.devices` vuoto, `response.charts`
   vuoto, `status == UPS_STATUS_UNSPECIFIED`.

Inoltre, `crac_server/component/ups/simulator/ups.py::status_for` ora solleva
`ConnectionError` per un device se la sua sezione in `ups.ini` ha
`fail = true` — coperto da `tests/component/ups/simulator/test_ups.py` e
usato per il test manuale end-to-end.

### Test plan manuale (eseguito su crac-test-stack, branch fix/44-ups-read-isolation)

1. Setup: `docker compose build crac-server && docker compose up -d` in
   `crac-test-stack` (build da sorgente locale del branch del fix).
2. Azione: `curl http://localhost:8000/ups/status`.
   Atteso: entrambi i device (`apc-3000`, `cyberpower`) presenti, 4 chart,
   `status: UPS_STATUS_NORMAL`. ✅ verificato.
3. Azione: nel container `crac-server`, settare `fail = true` nella sezione
   `[apc-3000]` di `/app/crac_server/component/ups/simulator/ups.ini`, poi
   ripetere `curl http://localhost:8000/ups/status`.
   Atteso: `devices` contiene solo `cyberpower`, 2 chart (solo cyberpower),
   `status` resta `UPS_STATUS_NORMAL` (non un errore/500), log di
   `crac-server` contiene una riga `ERROR ... Impossibile leggere l'UPS
   apc-3000: ...`. ✅ verificato.
4. Azione: rimuovere `ups.ini` dal container e ripetere il curl.
   Atteso: entrambi i device tornano presenti (il simulatore rigenera i
   default). ✅ verificato, stack fermato con `docker compose down` a fine
   test.
