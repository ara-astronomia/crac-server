# Piano — #74 Blocco di sicurezza per meteo pericoloso

Branch: `fix/74-safety-blocks-meteo` (da `main` @ `253724e`).
Issue: https://github.com/ara-astronomia/crac-server/issues/74

## 1. Cosa dice l'issue (e cosa e' emerso in piu')

L'issue riporta due difetti, entrambi **verificati su `main`**:

1. `block_on_unspecified` e' letta in `roof_handler.py:31` e `curtains_handler.py:27`
   ma non esiste nella sezione `[weather]` di `config.ini`. Confermato a runtime:
   `Config.getBoolean("block_on_unspecified", "weather")` torna `None`.
   Il blocco su meteo `UNSPECIFIED` e' quindi spento oggi, in silenzio.
2. `button_handler.py:49` contiene `mediator.is_disabled = False #True`:
   l'accensione del telescopio non viene mai bloccata con meteo `DANGER`.

### Ricostruzione storica del punto 2 (richiesta dall'issue)

L'issue chiedeva di verificare se il `#True` fosse deliberato. Non lo e':

- Introdotto da `b4d39c3` (spider65, 28 nov 2025 12:10:29), commit di **una sola
  riga**, messaggio "change setting mediator.is_disable=False".
- Il commit **precedente**, `e6ff3f5`, e' di **58 secondi prima** e tocca solo
  `config.ini`: punta il meteo a un IP di rete locale e allarga tutte le soglie
  (temperatura 40 -> 55, vento 30 -> 70, raffiche 30 -> 80, rain_rate 10 -> 40).
  Il quadro e' una sessione di debug in cui il meteo risultava DANGER e bloccava
  il lavoro: prima si allargano le soglie, poi si disattiva il blocco lasciando
  `#True` come promemoria.
- Sopravvissuto perche' `b4d39c3` vive solo su `origin/feature/uv-migration-and-docs`
  ed e' arrivato su `main` schiacciato nello squash della PR #45, in mezzo a ~100
  commit tipo `fix`, `add debug`, `delete print of debug`.
- Due conferme che era temporaneo: le soglie gonfiate dello stesso branch sono
  gia' tornate ai valori sani su `main` (l'URL locale e' stato sistemato da #67),
  e `RoofWeatherHandler`/`CurtainsWeatherHandler`, non toccati, usano `True`.

Verdetto: refuso. `True` va rimesso.

## 2. Ambiente di esecuzione

- **uv nativo**, non container: `uv` presente, `pyproject.toml` + `uv.lock` nel repo.
- Test: `uv run python -m unittest discover -s tests`.
- **Baseline verificata prima di toccare codice: 115 test, OK.**
- Il container di `crac-test-stack` serve solo per la verifica manuale finale
  (sezione 5), non per il ciclo di sviluppo.

## 3. Verifiche di configurazione eseguite

| Verifica | Risultato |
|---|---|
| `Config.getBoolean("block_on_unspecified", "weather")` | `None` — bug confermato |
| `[weather]` in `config.ini` | contiene solo `url`, `fallback_url`, `time_format`, `time_expired`, `retry_interval` |
| Esiste gia' un pattern "chiave obbligatoria"? | Si': `Config.getRequiredFloat` (`config.py:38`), aggiunta per la stessa ragione — **da riusare, non reinventare** |
| Test esistenti sugli handler | **nessuno**: `tests/` ha `component/`, `service/`, `test_config.py`. Nessun test cita `ButtonWeatherHandler` o `TELE_SWITCH` |
| Punto di lettura della config | livello modulo negli handler: una chiave mancante fa fallire l'**import**, quindi l'avvio. E' esattamente il "startup error" chiesto da #22 |

## 4. Prerequisiti e decisioni

- **Nessuna nuova dipendenza.** `strtobool` e' gia' importato in `config.py`.
- **Nessuna modifica a crac-protobuf** in questa issue (vedi sotto).
- **Default fail-safe**: `block_on_unspecified = true`. Cambia il comportamento
  odierno (che non blocca): e' il fix, non un effetto collaterale.
- **Impatto su `crac-test-stack`**: `WEATHER_TIME_EXPIRED=999999999` tiene il mock
  sempre "fresco", quindi lo stato non e' `UNSPECIFIED` e il default `true` non
  blocca lo stack. Da confermare nella verifica manuale.
- **Gotcha per i test**: `block_on_unspecified` e' una variabile di modulo letta
  all'import. Nei test va patchata come tale
  (`patch("crac_server.handler.roof_handler.block_on_unspecified", True)`),
  non via `Config`.
- **Fuori scope, issue #82**: l'indicatore visivo "sicurezze disattivate".
  Richiede `repeated string safety_overrides` in `WeatherResponse`
  (`crac-protobuf/interfaces/chart.proto`), bump a 0.1.23, aggiornamento del pin
  in `crac-server` (oggi `@0.1.22`) e il banner in `crac-cloud`. Tenuto fuori per
  non bloccare un fix di sicurezza dietro un lavoro su tre repo.

## 5. Implementazione

### 5.1 `crac_server/config.py`
Aggiungere `getRequiredBoolean(key, section)`, gemello di `getRequiredFloat`:
passa da `getValue` (che rispetta gli override da ambiente) e solleva su chiave
assente, valore vuoto o non booleano, invece di tornare `None`.

### 5.2 `crac_server/config.ini`
Sezione `[weather]`: aggiungere `block_on_unspecified = true`.

### 5.3 `crac_server/handler/roof_handler.py:31` e `curtains_handler.py:27`
`Config.getBoolean` -> `Config.getRequiredBoolean`.

### 5.4 `crac_server/handler/button_handler.py:49`
`mediator.is_disabled = False #True` -> `mediator.is_disabled = True`.

## 6. Strategia di test

Suite automatica disponibile: si procede in TDD (rosso prima).

### Test automatici da aggiungere

1. `tests/test_config.py`, nuova classe `TestGetRequiredBoolean`, sullo stampo di
   `TestGetRequiredFloat`: valori booleani validi, `raise` su valore assente,
   vuoto e non booleano.
2. `tests/handler/test_button_handler.py` (**directory nuova**): con meteo
   `WEATHER_STATUS_DANGER` e un `TELE_SWITCH` in `OFF` con azione `TURN_ON`,
   `ButtonWeatherHandler` deve lasciare `mediator.is_disabled is True`.
   E' il test di regressione che sarebbe servito a novembre 2025.
3. `tests/handler/test_roof_handler.py` e `test_curtains_handler.py`: con meteo
   `UNSPECIFIED`, l'apertura e' bloccata quando `block_on_unspecified` e' `True`
   e consentita quando e' `False`.

Vincolo: la suite deve restare verde (115 test + i nuovi).

### Verifica manuale sul test-stack

Il mock meteo (`crac_server/static/meteo_mock.json`) e' un file statico
modificabile, quindi lo stato meteo e' pilotabile a mano:

1. `docker compose up -d` da `crac-test-stack`.
2. Stato iniziale (mock invariato, meteo normale): il bottone di accensione
   telescopio in crac-cloud e' **abilitato**.
3. Portare `windSpeed` del mock oltre la soglia `error` (36) — es. `40,0` —
   e `docker compose restart crac-server`.
4. Atteso: meteo `DANGER` e bottone di accensione telescopio **disabilitato**.
   Prima di questo fix resta abilitato: e' la dimostrazione del bug.
5. Ripristinare il mock.
