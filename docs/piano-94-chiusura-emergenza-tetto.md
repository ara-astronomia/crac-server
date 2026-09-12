# Piano — #94 La chiusura d'emergenza per maltempo non chiude il tetto

Branch: `fix/94-chiusura-emergenza-tetto` (da `main` @ `2ff4136`).
Issue: https://github.com/ara-astronomia/crac-server/issues/94 (issue aperta)

## 0. Come riprendere

```bash
cd ../crac-server
git checkout fix/94-chiusura-emergenza-tetto
uv run python -m unittest discover -s tests    # baseline attesa: 219 test, OK (~32s)
```

Nessun file di codice ancora toccato: si parte dal test rosso.

## 1. Cosa dice l'issue, e cosa è stato verificato in più

L'issue è confermata leggendo il codice su `main` @ `2ff4136`:

- `WeatherService.GetStatus` (`crac_server/service/weather_service.py:52-58`) avvia
  `self.t = Thread(target=self._emergency_closure)` quando il meteo è `DANGER`.
- `_emergency_closure` è un metodo **sincrono** che gira in quel thread e alla riga
  `ROOF.close()` costruisce una coroutine e la scarta: `RoofControl.close` e
  `MockRoofControl.close` sono entrambe `async def`. Il motore non viene mai toccato.
- Tutto il resto della sequenza (`TELESCOPE.queue_park()`, `CURTAIN_*.disable()`,
  `SWITCHES[TELE_SWITCH].off()`) è sincrono e funziona.
- `tests/service/test_weather_service.py::test_status_danger_close_crac` sostituisce
  `_emergency_closure` con un `MagicMock` e verifica solo che venga chiamata: il corpo
  non lo esegue nessun test.

Emerso in più rispetto al testo dell'issue:

- **`self.t` non torna mai a `None` se la sequenza solleva**. Il reset è l'ultima riga
  del `with self.lock`, quindi qualsiasi eccezione a metà lascia `self.t` valorizzato e
  la guardia `self.t == None` in `GetStatus` **impedisce per sempre** un'altra chiusura
  d'emergenza per tutta la vita del processo. In un percorso di sicurezza è un difetto
  della stessa famiglia di quello segnalato, e costa un `try/finally`.
- `RoofControl.close()` **restituisce** `not self.is_blocked`: l'esito c'è già, oggi
  viene buttato via insieme alla coroutine. È il dato che serve per il log di esito
  chiesto dall'issue, non serve inventarne altri.

## 2. Ambiente di esecuzione

**uv nativo**, non container: `uv 0.12.5` presente, `pyproject.toml` + `uv.lock` nel repo.
Il test stack Docker qui non serve — anzi non vedrebbe il difetto, perché monta il
simulatore; il test gira sulla classe di produzione con il pin factory finto di gpiozero.

## 3. Verifiche di configurazione eseguite

| cosa | risultato |
|---|---|
| `crac_server/config.ini:10` `gpio_mock = on` | il singleton `ROOF` è un `MockRoofControl` → il test patcherà `weather_service.ROOF` con un `RoofControl` **vero** |
| `crac_server/config.ini:118` `roof_timeout = 50` | `wait_for_active` scade a 50s: nel test i finecorsa vanno pilotati prima della chiamata, altrimenti la suite si pianta per 50s |
| `tests/__init__.py` | monta già `Device.pin_factory = MockFactory()`: niente da aggiungere |
| `tests/component/roof/test_roof_control.py` | istanzia già il `RoofControl` reale e fa `Device.pin_factory.reset()` in `setUpClass`/`tearDown` per non incappare in `GPIOPinInUse`: stesso schema da riusare, non da reinventare |
| polarità dei finecorsa | `DigitalInputDevice(..., pull_up=True)` → `drive_low()` = finecorsa **attivo**, `drive_high()` = inattivo |
| baseline suite | 219 test, OK, ~32s |

## 4. Prerequisiti

Nessuna dipendenza nuova, nessun segreto, nessuna configurazione esterna.
Codice esistente da riusare invece di duplicare:

- `asyncio.run_coroutine_threadsafe` (stdlib) per consegnare la coroutine al loop:
  è il ponte thread → loop già corretto, non serve un executor o una coda nostra.
- `asyncio.get_running_loop()` dentro `GetStatus`, che **gira già sul loop**: il
  riferimento si cattura lì e si passa al thread. Non usare `get_event_loop()` dal
  thread, che lì non trova nessun loop.
- Il pattern di `RoofHandler` (`handler/roof_handler.py:93-99`) conferma che l'apertura
  e la chiusura da comando operatore vivono già sul loop: la chiusura d'emergenza si
  allinea a quello, non introduce una seconda strada.

Vincolo noto e **fuori scope**, da non risolvere qui: su hardware vero `RoofControl.close()`
blocca il loop per tutta la corsa (fino a `roof_timeout`), ed è esattamente
ara-astronomia/crac-server#95 (issue aperta). Questo piano fa arrivare il comando al
motore; spostare l'attesa fuori dal loop è il lavoro di #95, che tocca lo stesso metodo.
Farli insieme mescolerebbe due verifiche diverse nella stessa PR.

## 5. Strategia di test

Suite automatica disponibile (`unittest`), quindi niente test plan manuale. Tre test
nuovi in `tests/service/test_weather_service.py`, **rossi prima della modifica**:

1. **Il tetto risulta chiuso alla fine della sequenza** — il test che l'issue chiede.
   `weather_service.ROOF` patchato con un `RoofControl` reale, `TELESCOPE`/`CURTAIN_EAST`/
   `CURTAIN_WEST`/`SWITCHES` con dei doppi che dichiarano subito lo stato finale
   (telescopio `PARKED`, tende `CURTAIN_DISABLED`) per non far girare a vuoto i
   `while ... sleep(1)`. Partenza: motore acceso, finecorsa di chiusura già attivo
   (il tetto "arriva a fine corsa"). Il corpo si esegue davvero, da un thread, con
   `await asyncio.to_thread(service._emergency_closure, asyncio.get_running_loop())`.
   Asserzione: `roof.get_status() is RoofStatus.ROOF_CLOSED`.
   Oggi è rosso: la coroutine non parte, il motore resta acceso, lo stato è `ROOF_CLOSING`.
2. **L'esito della chiusura finisce a log, non solo l'intenzione** — con la chiusura
   bloccata (`wait_for_active` che torna `False`, come già fa
   `test_when_roof_is_blocked_while_opening_then_it_will_close`) la sequenza deve
   registrare a ERROR che il tetto **non** si è chiuso. Oggi non lo registra nessuno:
   "close the roof" viene scritto comunque.
3. **Una sequenza che solleva non blocca le chiusure successive** — `self.t` deve tornare
   a `None` anche se un passo lancia, altrimenti la protezione si disarma da sola.

Modifica prevista, dopo il rosso (`crac_server/service/weather_service.py`):

- `GetStatus`: `Thread(target=self._emergency_closure, args=(asyncio.get_running_loop(),))`
- `_emergency_closure(self, loop)`: `ROOF.close()` diventa
  `asyncio.run_coroutine_threadsafe(ROOF.close(), loop).result()`, con log dell'esito
  restituito, e il corpo dentro `try/finally` che azzera `self.t`.

Verifica finale: suite intera verde (220+ test) e i tre test nuovi rossi su `main`.

---

## Aggiornamento: ambito allargato in corso d'opera

La PR aperta ara-astronomia/crac-server#98 chiude anche la issue aperta
ara-astronomia/crac-server#95, che questo piano dava per fuori scope. Motivo:
la prova sullo stack ha mostrato che il simulatore `MockRoofControl` faceva
mentire il log dell'esito (`the roof did not close` a tetto chiuso), e che
scavalcando `open`/`close` lo stack non eseguiva mai il codice di produzione -
proprio quello dove vivevano sia la coroutine mai avviata sia il blocco
dell'event loop. Tolto il simulatore del componente in favore di un pin del
motore cablato ai finecorsa (`MockRoofMotorPin`), l'attesa bloccante doveva
uscire dal loop nella stessa PR, altrimenti lo stack si sarebbe congelato per
dieci secondi a ogni corsa. Decisione presa con l'utente.
