# Fatto — #99 (config letto una volta sola) + #78 (test sulla loro configurazione)

Branch: `fix/99-78-config-caricato-una-volta` (da `main` @ `1c79f26`), **due commit
locali, non pushati**.
Issue: crac-server#99 (aperta) e crac-server#78 (aperta).

```bash
cd ../crac-server
git checkout fix/99-78-config-caricato-una-volta
uv run python -m unittest discover -t . -s tests    # 233 test, OK (~15s)
```

## Perché insieme

Non sono la stessa storia, ma mancava lo stesso pezzo a entrambe: **non esisteva un
posto dove `config.ini` viene caricato**. Ogni getter costruiva una `Config` e
riparsava il file (#99), e per lo stesso motivo i test non avevano una leva per
sostituirlo e leggevano quello di produzione (#78). Il primo commit crea quel punto,
il secondo lo punta a un file dei test.

## Commit 1 — #99

`ConfigParser` a livello di modulo, riparsato solo quando cambia l'identità del file
su disco (percorso, `st_mtime_ns`, dimensione). La strada è quella decisa nella issue:
la modifica a caldo resta viva ovunque, produzione compresa.

Misure sullo stack di test, container ricostruito:

| | prima (issue) | dopo |
|---|---|---|
| `WeatherConverter.convert()` | 56.4 ms | **1.29 ms** |
| riletture di `config.ini` in 20 conversioni | 1080 | **0** |
| `/roof/status` (browser → crac-cloud) | 58 ms | **5 ms** |
| `/charts/status` | 60 ms | **5 ms** |
| `/buttons/status` | 70 ms | **10 ms** |

Modifica a caldo verificata nel container: `roof_timeout` cambiato nel file e riletto
dallo stesso processo senza riavvio (50 → 7 → 50).

Utile per crac-cloud#23 (issue aperta, deadline gRPC): quei 60 ms non erano il costo
della lettura, erano rilettura di file.

## Commit 2 — #78

La suite gira su `tests/config.ini`, scelto impostando `CRAC_CONFIG_PATH` in
`tests/__init__.py` prima di qualunque import: i componenti costruiscono i singleton
mentre vengono importati, e `crac_server/__init__.py` legge `gpio_mock` prima ancora
di arrivare a loro, quindi più tardi non c'è momento utile. Il file è una copia di
quello di produzione con indirizzi di rete irraggiungibili (`*.invalid`).

Prova: spostando via `crac_server/config.ini` la suite resta verde — non lo legge più
nessuno.

**Trovato per strada**: `tests/__init__.py` non veniva proprio eseguito. Con
`discover -s tests`, `tests/` diventa il top level e i moduli si chiamano
`component.roof.test_...`: il package non viene mai importato. Il setup della pin
factory mock che sta lì dentro non è mai girato — a montare il mock era
`crac_server/__init__.py`, cioè di nuovo il `config.ini` di produzione. CI e AGENTS.md
ora usano `discover -t . -s tests`.

La strada indicata nella issue (patch su `Config` file per file, come #76) resta
valida dove un test vuole un valore suo, e i test dell'UPS la usano già: il file dei
test toglie la dipendenza di default, il patch resta per i casi specifici.

## Da fare al risveglio

1. `git push -u origin fix/99-78-config-caricato-una-volta` (non fatto: il push lo
   decide l'utente).
2. PR con corpo che chiuda entrambe:

   > Il config non veniva caricato in un posto solo: ogni getter riparsava il file, e
   > per lo stesso motivo i test non avevano dove sostituirlo e leggevano quello di
   > produzione.
   >
   > Closes #99
   > Closes #78

3. Da decidere con calma: `tests/config.ini` oggi è una copia integrale di quello di
   produzione, commenti sul cablaggio compresi. Si può potare alle sole sezioni che i
   test leggono (~70 chiavi tracciate), ma una chiave che manca fallisce con
   `KeyError`, quindi la copia è la versione che non chiede manutenzione.
