# AGENTS.md

Server gRPC per il controllo dell'osservatorio astronomico ARA (Ara
Astronomia, Frasso Sabino): tetto, telescopio, tende, alimentatori (UPS),
luci, e copertura a petali dello specchio. Espone RPC consumate da
`crac-cloud` (la GUI web).

## Comandi

```bash
uv sync                          # installa dipendenze
python -m crac_server.app        # avvia il server gRPC (porta 50051)
python -m unittest discover -s tests   # suite di test (unittest, NON pytest)
autopep8 --in-place --recursive crac_server/   # format
python -m grpc_tools.protoc -I proto --python_out=. --grpc_python_out=. proto/*.proto  # rigenera stub protobuf, quando cambia crac-protobuf
```

Richiede Python 3.12 (vincolo esplicito in `pyproject.toml`,
`>=3.12,<3.13`).

## Stack

- Python 3.12, gRPC (asyncio), gpiozero + lgpio per il GPIO
- `crac-protobuf` come dipendenza git diretta (vedi ref esatto in
  `pyproject.toml` - cambia spesso durante lo sviluppo di feature nuove,
  controllare che combaci col branch di crac-protobuf che si vuole testare)
- astropy/numpy per i calcoli di posizione (alt/az ↔ RA/Dec)
- Test: `unittest` della stdlib, non pytest - nessun `conftest.py`/fixture

## Mappa del repo

```
crac_server/
  app.py                    # entrypoint, avvio server gRPC + logging
  config.py                 # lettura config.ini, override via env {SECTION}_{KEY}
  component/                # driver hardware/protocollo
    telescope/               # un sotto-modulo per driver: indigo, indi, ascom_hub, theskyx, simulator
    curtains/, roof/         # controllo GPIO via gpiozero (simulator/ per mock)
    cover_mirror/            # copertura a petali via INDIGO
    indigo_client.py         # client INDIGO condiviso (connessione persistente, cache proprietà)
  service/                  # implementazioni dei servicer gRPC (uno per dominio)
  handler/                  # catena di responsabilità per la logica di business per-azione
  converter/                # mediator/converter tra richieste gRPC e stato interno
tests/                      # rispecchia la struttura di crac_server/
```

## Vincoli e gotcha non ovvi

- **Driver telescopio "indigo"**: non forza più la connessione al device da
  solo - il telescopio va connesso manualmente dal pannello INDIGO prima
  che crac lo usi (replica il workflow reale: l'operatore collega il
  telescopio da INDIGO prima di accenderlo su crac). Se il device non
  risulta connesso su INDIGO, lo stato riportato è `LOST`, non un falso
  "connesso".
- **`IndigoClient`** (`component/indigo_client.py`) mantiene connessione
  TCP persistente + cache proprietà via broadcast INDIGO - non fa polling
  di rete. Il polling che *sembra* esserci (`polling_interval` nel
  telescopio) è solo la frequenza con cui il thread interno ricalcola lo
  stato dalla cache già aggiornata in tempo reale.
- **Park nativo INDIGO**: `park()` manda *solo* `MOUNT_PARK` - mai un
  `UNPARK` prima. `indigo_mount_lx200` (TeenAstro) scarta il park finché il
  mount risulta `parked`/`parking`/`homing`, ma echeggia comunque
  `PARKED=true` (`indigo_property_copy_values` gira prima di quella
  guardia): l'unpark è asincrono, quindi un park mandato subito dopo
  finiva sempre scartato e crac passava a PARKED con il telescopio fermo
  dov'era.
- **`MOUNT_PARK_POSITION` è roba da simulatore**: la scriviamo (HA/DEC, non
  alt/az - le uniche coordinate time-invariant per un punto fisso) solo se
  il driver la espone davvero e solo a mount sparcheggiato (da parcheggiato
  la scrittura viene rifiutata). Su un mount reale la posizione di park vive
  nel mount e quella proprietà non esiste nemmeno. Nessun
  `CONFIG_SAVE`/`CONFIG_LOAD`: alla riconnessione `_park_position_synced`
  si azzera e la posizione viene rimandata al primo park utile.
- **Dopo il park non si tocca `MOUNT_TRACKING`**: parcheggiare spegne già
  il tracking da solo, e il comando arriverebbe a mount parcheggiato (dove
  viene rifiutato) o in pieno park.
- **Coda comandi telescopio** (`Telescope._jobs`): va sempre deduplicata
  (vedi `queue_set_speed`) - senza dedup, un client che pollasse più spesso
  del ciclo interno di retrieve() farebbe crescere la coda senza limite,
  ritardando i comandi reali (park/flat) dietro job ridondanti.
- **Test roof**: serve `Device.pin_factory.reset()` in `setUpClass`/
  `tearDown` - un singolo eager (`ROOF` in `component/roof/__init__.py`,
  istanziato all'import) riserva il pin GPIO mock prima ancora che parta
  il primo test.

## Convenzioni di stile

- **Async/sync safety (gRPC) — mandato critico**: i servicer sono `async def`.
  Non chiamare mai codice bloccante direttamente al loro interno (attese
  GPIO, richieste sincrone tipo `urllib`) - usare `asyncio.to_thread()` /
  `run_in_executor()`. Le procedure di emergenza (es. chiusura tetto per
  meteo/UPS) devono restare awaitable: lanciarle in un `Thread` normale e
  chiamare da lì metodi `async` (es. `ROOF.close()`) senza un event loop è
  un bug ricorrente.
- Naming: moduli/package `snake_case`, classi `PascalCase`, funzioni/variabili
  `snake_case`, costanti `UPPER_SNAKE_CASE`, membri privati con prefisso `_`.
- Import in tre gruppi separati da riga vuota: stdlib, third-party (grpc,
  astropy, ecc.), moduli locali.

## Regole per agenti

- **Mai eseguire `git push`** senza che sia il passo esplicitamente
  richiesto dall'utente in quel momento - è un'azione riservata all'utente
  o va confermata volta per volta, non presunta da un'autorizzazione
  precedente.
- Verificare `git config user.email` prima di un commit, se rilevante per
  il progetto.
- Un commit va fatto solo se i test rilevanti passano.
- Preferire commit atomici e descrittivi a un unico commit "raccogli tutto".

## Repo correlati

Questo progetto è composto da più repo, clonati come sibling
(`../crac-cloud`, `../crac-protobuf`, `../RC_Cover`) o orchestrati insieme
da `../crac-test-stack`. Quando il lavoro tocca più di un repo:

1. **Cerca prima sul filesystem**: se `../<repo>` esiste come clone locale,
   usalo. Controlla `git -C ../<repo> branch --show-current` prima di
   leggere il suo file di contesto o il suo codice - i repo di questo
   progetto sono spesso su branch feature specifici (non `main`), e
   leggere main quando in realtà serve il branch in lavorazione dà un
   quadro sbagliato/obsoleto.
2. **Fallback su GitHub** se il repo non è clonato localmente:
   `https://github.com/ara-astronomia/<repo>` (org `ara-astronomia`).

Repo del progetto:
- `crac-cloud` - GUI web FastAPI, consuma le RPC di questo server
- `crac-protobuf` - contratti `.proto` condivisi (dipendenza git di questo
  repo e di crac-cloud)
- `crac-test-stack` - stack Docker per testare tutto insieme in locale
  (crac-server + crac-cloud + un vero server INDIGO con simulatori)
- `RC_Cover` - driver INDIGO custom per la copertura a petali dello specchio
  (repo privato, C)
