# Piano — #130 e #132 chiudono/spengono i pin ad ogni riavvio del processo

Branch: `fix/130-132-gpio-non-scrive-pin-al-riavvio` (da `main` @ `745dbb7`).
Issue: https://github.com/ara-astronomia/crac-server/issues/130 (aperta)
Issue: https://github.com/ara-astronomia/crac-server/issues/132 (aperta)

## 0. Come riprendere

```bash
cd ../crac-server
git checkout fix/130-132-gpio-non-scrive-pin-al-riavvio
uv run python -m unittest discover    # baseline attesa: 273 test, OK (~5s)
```

**Va lanciata dalla root, senza `-s tests`**: con `-s tests`, `tests/__init__.py`
(mock della pin factory + config di test) non gira come package init e la
suite fallisce con `Device.pin_factory` a `None` su tutto ciò che tocca GPIO
(10 errori + 2 failure fantasma). Documentato in `AGENTS.md:139-141`.

## 1. Cosa dicono le issue

Stesso bug in due file: `RoofControl.__init__` (`roof_control.py:14`) e
`ButtonControl.__init__` (`button_control.py:14`) costruiscono
`OutputDevice(pin)` senza `initial_value`. gpiozero scrive subito `False`
(= "off") sul pin fisico in costruzione — prima e fuori da qualunque
controllo di sicurezza (`roof_service.py`) o log. Per il tetto: comando di
chiusura implicito. Per i quattro switch (`TELE_SWITCH`, `CCD_SWITCH`,
`FLAT_LIGHT`, `DOME_LIGHT`): spegnimento implicito, anche a metà
osservazione.

Riguarda solo il riavvio del *processo* col Raspberry Pi acceso (crash,
`systemctl restart` — il deploy vero in `.github/workflows/deploy.yml:61` è
esattamente questo). Un reboot completo del Pi è un problema diverso e non
risolvibile in software: crac-server#131 (aperta, `needs-decision`), fuori
scope qui.

## 2. Ambiente di esecuzione

`uv` nativo, non lo stack Docker: monta il simulatore del tetto
(`roof_pins.py`), che non vedrebbe questo difetto perché testa solo il
comportamento a runtime, non cosa succede *in costruzione*. Stesso schema
già usato in `docs/piano-94-chiusura-emergenza-tetto.md`.

## 3. Prerequisiti

Nessuna dipendenza nuova, nessuna configurazione esterna. Codice da riusare:

- `tests/component/roof/test_roof_control.py:166` — pattern per prendere il
  pin direttamente da `Device.pin_factory.pin(Config.getInt(...))` e
  pilotarlo prima di costruire il componente. Stesso pattern serve per
  precaricare lo stato del pin *prima* di costruire `RoofControl`/
  `ButtonControl` e verificare che la costruzione non lo tocchi.
- `tests/__init__.py` monta già `Device.pin_factory = MockFactory()`: niente
  da aggiungere lì.

## 4. Strategia di test (TDD, rosso prima della modifica)

Suite automatica (`unittest` + `MockFactory`), niente test plan manuale.

1. **`tests/component/roof/test_roof_control.py`** — nuovo test nella classe
   `TestRoofControl`: riservare il pin del motore con
   `Device.pin_factory.pin(Config.getInt("switch_roof", "roof_board"))` e
   pilotarlo `drive_high()` (simula "tetto aperto, relè energizzato")
   *prima* di costruire `RoofControl()`. Dopo la costruzione, assert che lo
   stato del pin sia rimasto invariato (`True`). Oggi è rosso: il
   costruttore lo forza a `False`.
2. **`tests/component/test_button_control.py`** (nuovo file) — stesso
   schema su `ButtonControl`: pin pilotato `drive_high()` prima della
   costruzione, invariato dopo.

Modifica prevista, dopo il rosso:

- `roof_control.py:14`: `OutputDevice(pin, initial_value=None)`
- `button_control.py:14`: `OutputDevice(pin, initial_value=None)`

Verifica finale: suite intera verde (275 test).

## 5. Prima del merge — verifica su hardware vero (non automatizzabile)

Documentata in crac-server#130: con il tetto **aperto** su hardware vero,
lanciare `systemctl restart crac-server` e verificare che il relè del tetto
non scatti (il tetto resta fermo/aperto). Se scatta, il fix non basta e la
issue va riaperta con quello che si osserva. Da aggiungere come checklist
esplicita nella PR.
