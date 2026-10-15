# AGENTS.md

Server gRPC per il controllo dell'osservatorio astronomico ARA (Ara
Astronomia, Frasso Sabino): tetto, telescopio, tende, alimentatori (UPS),
luci, e copertura a petali dello specchio. Espone RPC consumate da
`crac-cloud` (la GUI web).

## Comandi

```bash
uv sync                          # installa dipendenze
python -m crac_server.app        # avvia il server gRPC (porta 50051)
python -m unittest discover      # suite di test (unittest, NON pytest)
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
  config.py                 # lettura config.ini (percorso da CRAC_CONFIG_PATH),
                            # override dei valori via env {SECTION}_{KEY}
  component/                # driver hardware/protocollo
    telescope/               # un sotto-modulo per driver: indigo, simulator,
                             # pluggable via entry point (vedi sotto)
    curtains/, roof/         # controllo GPIO via gpiozero (simulator/ per mock)
    cover_mirror/            # copertura a petali via INDIGO
    indigo_client.py         # client INDIGO condiviso (connessione persistente, cache proprietà)
  service/                  # implementazioni dei servicer gRPC (uno per dominio)
  handler/                  # catena di responsabilità per la logica di business per-azione
  converter/                # mediator/converter tra richieste gRPC e stato interno
tests/                      # rispecchia la struttura di crac_server/
```

## Vincoli e gotcha non ovvi

- **Il tetto sta aperto solo finché il relè è eccitato**: `RoofControl.open()`
  accende il motore e `close()` lo spegne, quindi un processo che muore lascia
  il pin rilasciato e il tetto va verso la chiusura. È un fail-safe, ed è
  **altamente probabile** ma non verificato sull'hardware: dal codice si legge
  solo che aperto = eccitato, cosa faccia il relè senza corrente lo dice il
  cablaggio in cupola.
- **Una corsa interrotta lascia il tetto a metà**: l'attesa del finecorsa gira
  fuori dal loop (`asyncio.to_thread`), quindi un arresto la cancella con il
  motore ancora eccitato. Viene registrata a ERROR, ed è l'unica traccia che
  resta dopo un riavvio. Attenzione a una conseguenza non ovvia: il processo
  non esce subito, perché `asyncio.run()` si unisce al thread rimasto dentro
  `wait_for_active` - aspetta il `roof_timeout` residuo (50s), e su
  `docker compose stop` scadono prima i 10 secondi di grazia.
- **Le tende si chiudono sul finecorsa, si aprono sull'encoder**: una tenda è
  giù solo se il finecorsa di chiusura è attivo, e in discesa l'encoder non
  la ferma. In salita il finecorsa di apertura non si raggiunge: l'apertura
  totale è `n_step_corsa`, e `n_step_sicurezza` è sia l'arresto di sicurezza
  sia il massimo dell'encoder. All'avvio `build_curtain()` chiama
  `disable(power_motor=True)`: ogni tenda scende e si disattiva.
- **Chi riaccende il motore di una tenda**: solo `enable()` e il DISABLE
  dell'operatore (`disable(power_motor=True)`, primo handler della catena in
  `CurtainsService`, quindi vale anche a tetto chiuso o telescopio spento).
  Le disattivazioni automatiche (tetto, telescopio, meteo) chiamano
  `disable()` a ogni poll e non lo riaccendono mai: una tenda giù con il
  finecorsa guasto sembra a metà corsa.
- **Inversione del motore delle tende**: prima di girare nell'altro verso il
  motore resta fermo `reverse_pause` secondi contati dallo stop, su un
  `threading.Timer`. Un comando durante la pausa non la allunga, cambia solo
  il bersaglio; a fine pausa la tenda va verso il bersaglio di quel momento.
  Il lock di `Curtain` è un `Lock` semplice preso solo dai metodi pubblici e
  dalle callback GPIO: un metodo che lo tiene non deve chiamarne un altro
  che lo prende, e nessuno deve dormire tenendolo (blocca l'event loop gRPC
  e le callback di lgpio, che arrivano tutte da un thread solo).
- **La tenda simulata si muove anche con il motore disabilitato**
  (`MockCurtain` guarda solo `motor.value`) e parte sempre sul finecorsa:
  sullo stack non si riproducono né una tenda a metà corsa all'avvio né una
  tenda col motore spento fuori dal finecorsa. Questi casi li coprono solo i
  test automatici.
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
- **Il sito dell'osservatorio non si scrive mai sul mount**:
  `GEOGRAPHIC_COORDINATES` si legge, non si manda. Sul mount il sito è il
  riferimento di ogni conversione che il mount fa, e riscriverlo dall'esterno
  lo invalida - in produzione ha azzerato lat/lon del TeenAstro. Ne segue un
  invariante implicito: le ALT/AZ di `MOUNT_HORIZONTAL_COORDINATES` le calcola
  INDIGO col sito configurato *nel mount*, mentre i target di park e flat li
  calcola crac con `[geography]` del `config.ini`. I due devono coincidere. Se
  divergono, il telescopio atterra fuori bersaglio e `_retrieve_status`
  classifica male i quadranti senza che niente lo segnali. Chi può farli
  divergere: un `indigo_agent_mount` con `AGENT_SITE_DATA_SOURCE = HOST`, che
  propaga il proprio (0,0 per default) al device che adotta; l'operatore da
  `/ctrl.html`; un mount riconfigurato.
- **La quota del sito dal mount non arriva mai**, ed è una lacuna del driver,
  non del mount: il firmware TeenAstro la espone (`:Ge#` per leggerla, `:Se#`
  per scriverla), ma `meade_get_site()` in `indigo_mount_lx200.c` chiede solo
  `:Gt#`/`:Gg#` e `meade_set_site()` la manda solo ai mount NYX. Irrilevante
  per le alt/az (astropy senza pressione non modella la rifrazione, e la quota
  non sposta un oggetto stellare); conta invece per l'airmass, che crac-cloud
  calcola su `[geography] height` via `geographic_service`.
- **Dopo il park non si tocca `MOUNT_TRACKING`**: parcheggiare spegne già
  il tracking da solo, e il comando arriverebbe a mount parcheggiato (dove
  viene rifiutato) o in pieno park.
- **La sicurezza meteo gira da sola**: `WeatherService.watch()` parte con il
  server (`app.serve()`) e chiama `check()` ogni `[weather] check_interval`
  secondi (obbligatoria, almeno 30: altrimenti il server non parte).
  `GetStatus` chiama lo stesso `check()`, quindi crac-cloud non serve più
  per far partire la chiusura d'emergenza. La guardia contro due chiusure
  insieme è `self.t`, ed è sicura solo perché ciclo e RPC girano sullo
  stesso event loop, senza `await` fra il controllo e l'assegnazione: non
  aggiungerne uno lì in mezzo. A tetto `ROOF_CLOSED` la chiusura non parte.
  Ogni guasto di lettura, compreso il dato in cache scaduto dopo un
  aggiornamento fallito, si scrive una volta con `StatusLogger`; la ripresa
  solo con un dato fresco.
- **Coda comandi telescopio** (`Telescope._jobs`): `_enqueue()` deduplica sul
  job intero (stesso dizionario azione+argomenti già in coda) - senza dedup,
  un client che pollasse più spesso del ciclo interno di retrieve() farebbe
  crescere la coda senza limite, ritardando i comandi reali dietro job
  ridondanti.
- **Un driver telescopio esterno si registra come entry point**, non va
  copiato dentro questo repo: nel `pyproject.toml` del pacchetto di terzi,
  `[project.entry-points."crac_server.telescope_drivers"]` con
  `name = "my_package.telescope:Telescope"`. `config.ini` continua a
  usare un nome breve (`driver = name`), esattamente come oggi con
  `indigo`/`simulator` - anche questi due sono registrati nello stesso
  modo, nel `pyproject.toml` di questo repo, non hardcoded nel factory
  (`crac_server/component/telescope/__init__.py`). Il contratto da
  implementare è la classe astratta `Telescope`
  (`component/telescope/telescope.py`): quattro metodi
  (`set_speed`/`park`/`flat`/`retrieve`), `retrieve()` ritorna un
  `TelescopeReading` (NamedTuple: `eq_coords`, `aa_coords`, `speed`,
  `status`). `simulator` è il riferimento minimale; `conformance.py`
  nello stesso package offre un mixin di test (`TelescopeConformanceTestCase`,
  **non** un `TestCase` di per sé - lo raccoglierebbe anche `unittest
  discover` di questo repo) che un terzo può mischiare nel proprio
  `unittest.TestCase` per verificare la forma del contratto. Nessuna
  promessa di stabilità sull'interfaccia fra versioni.
- **Dopo aver toccato gli entry point in `pyproject.toml`, rilanciare
  `uv sync`**: sono letti dai metadati del pacchetto installato
  (`crac_server.egg-info/entry_points.txt`), non dal file al volo -
  senza un resync anche `indigo`/`simulator` risultano "non registrati"
  e `telescope()` fallisce all'avvio.
- **La suite va lanciata dalla root** (`python -m unittest discover`):
  `tests/__init__.py` e' il setup globale (pin factory mock e configurazione
  dei test) e gira solo se `tests` viene importato come package. Con
  `discover -s tests` unittest prende `tests/` come top level, quel setup non
  viene eseguito e due test lo dicono fallendo.
- **La suite legge `tests/config.ini`**, scelto da `CRAC_CONFIG_PATH` in
  `tests/__init__.py`. Una chiave nuova usata dal codice va aggiunta anche
  li', altrimenti i test falliscono con `KeyError`. Un test che vuole un
  valore suo fa `patch` su `Config`, come quelli dell'UPS.
- **I componenti si prendono chiamandoli**: `roof()`, `telescope()`,
  `curtain_east()`, `curtain_west()`, `weather()`, `switches()`,
  `cover_mirror()`. Costruiscono al primo uso e poi tengono l'istanza
  (`lru_cache`), quindi importare un modulo non legge configurazione e non
  apre pin - un test lo verifica importando in un processo puntato a un
  file di configurazione inesistente. Per lo stesso motivo la
  configurazione va letta dentro le funzioni: a livello di modulo si
  congela, e la rilettura a caldo di `Config` non ha piu' effetto.
  `app.py` li costruisce tutti all'avvio, cosi' un guasto si vede quando il
  servizio parte e non alla prima richiesta.
- **Chi monta il GPIO finto**: nei test `tests/__init__.py`, nello stack
  Docker `GPIOZERO_PIN_FACTORY=mock` (meccanismo di gpiozero). Da quando i
  componenti sono pigri, `Device.pin_factory` resta `None` finche' qualcuno
  non costruisce un device: chi ha bisogno della factory prima chiama
  `Device.ensure_pin_factory()`.
- **Test roof**: serve `Device.pin_factory.reset()` in `setUpClass`/
  `tearDown`, e `roof.cache_clear()` se il test vuole un tetto nuovo:
  l'istanza tenuta dalla cache trattiene i pin GPIO mock gia' riservati.
- **Mai assegnare attributi a una classe in un test** (`type(telescope()).polling
  = True`, `type(weather()).wind_speed = PropertyMock(...)`): resta per tutti
  i test dopo. Usare `patch.object(..., new_callable=PropertyMock)`, che
  dura solo il test. Un `polling` vero rimasto così ha fatto partire una
  chiusura d'emergenza vera in un test con meteo DANGER, appendendo la suite.

## Convenzioni di stile

Valgono le convenzioni Python delle PEP: in particolare PEP 8 (stile e nomi)
e PEP 257 (docstring). Le regole qui sotto sono più restrittive e prevalgono
dove ne parlano; per tutto il resto vale la PEP.

- **Async/sync safety (gRPC) — mandato critico**: i servicer sono `async def`.
  Non chiamare mai codice bloccante direttamente al loro interno (attese
  GPIO, richieste sincrone tipo `urllib`) - usare `asyncio.to_thread()` /
  `run_in_executor()`. Le procedure di emergenza (es. chiusura tetto per
  meteo/UPS) devono restare awaitable: lanciarle in un `Thread` normale e
  chiamare da lì metodi `async` (es. `ROOF.close()`) senza un event loop è
  un bug ricorrente.
- Naming: moduli/package `snake_case`, classi `PascalCase`, funzioni/variabili
  `snake_case`, costanti `UPPER_SNAKE_CASE`, in inglese.
- Membri interni con un trattino basso (`_on_switch`), anche quando una sottoclasse
  li usa. Mai `__on_switch__`: è riservato ai metodi speciali di Python e non
  rende niente privato. `__on_switch` (name mangling) solo se serve davvero
  nascondere il membro alle sottoclassi.
- **Commenti**: docstring sì, commenti inline no. Se un blocco ha bisogno di
  un commento per farsi capire, va riscritto: un metodo o una costante con un
  nome che dica quello che direbbe il commento. Il codice commentato si
  cancella, c'è git.
- Docstring e blocchi di commento al massimo di **3 righe**. Dicono cosa fa
  il codice adesso, mai com'era prima né di quanto è migliorato: la storia
  del difetto sta nel commit e nella PR.
- Docstring, commenti, messaggi di log ed eccezioni in **inglese**. Mai
  numeri di issue nel codice (`#44`): invecchiano, e il motivo legato a una
  storia va nel commit o nella PR.
- In `config.ini` i commenti servono, perché li legge chi configura il
  servizio: spiegano cablaggi e soglie che il nome della chiave non dice.
  Anche lì in inglese e corti.
- Nei test, asserzioni standard di `unittest.mock`
  (`assert_called_once_with`, `assert_not_called`, `assert_has_calls`).
  Da evitare solo le ricostruzioni a mano su `call_args_list`.
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
