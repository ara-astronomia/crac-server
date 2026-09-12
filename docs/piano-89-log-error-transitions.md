# Piano — #89 Il log a ERROR ha buchi: coprire le transizioni verso l'errore

Branch: `fix/89-log-error-transitions` (da `main` @ `cb476ec`).
Issue: https://github.com/ara-astronomia/crac-server/issues/89

## 0. Come riprendere

```bash
cd ../crac-server
git checkout fix/89-log-error-transitions
uv run python -m unittest discover -s tests    # baseline attesa: 175 test, OK
```

Nessun file di codice ancora toccato.

## 1. Cosa dice l'issue, e cosa ha aggiunto il planning

L'issue chiede tre cose: loggare le **transizioni** (non ogni lettura), un formato uniforme
e correlabile, e il **rientro** dall'errore.

Il planning ha aggiunto due punti non nell'issue:

- **Il vocabolario delle cause si definisce qui.** L'issue parla di "identificativo della
  causa" senza dire da dove esca. Non esiste ancora: l'enum sta in
  ara-astronomia/crac-protobuf#27 (issue aperta), che abbiamo deciso di lavorare *dopo*
  questa. Quindi le costanti nascono qui, in crac-server, e quando l'enum arrivera' saranno
  il suo mapping uno a uno. E' esattamente il motivo per cui #89 precede #27: il vocabolario
  viene validato sul campo prima di essere congelato nel contratto.
- **Il rumore non e' un problema.** A stack sano, in 120 secondi, il container produce zero
  righe `INFO` e zero `ERROR` (le 22.000 righe misurate sono tutte `DEBUG`, livello che il
  test-stack forza via `LOG_LEVEL`). La rotazione Docker e' `json-file`, `max-size=10m`,
  `max-file=3`: 30 MB che a livello di produzione coprono moltissimo tempo. Aggiungere le
  transizioni non intacca quella riserva, mentre loggare a ogni lettura si'.

## 2. Ambiente di esecuzione

- **uv nativo**: `uv run python -m unittest discover -s tests`. Baseline verificata: 175 test, OK.
- **Verifica manuale**: `crac-test-stack`, leggendo `docker logs`. Attenzione: il container
  gira con `LOG_LEVEL=DEBUG`, quindi per vedere l'effetto reale va filtrato per livello.
- `assertLogs` non e' mai stato usato nella suite: e' stdlib, nessuna dipendenza nuova.

## 3. Verifiche eseguite

| verifica | risultato |
|---|---|
| formato del log | `logging.conf` ha gia' `asctime`, `name`, `levelname`, `filename`, `lineno`: ora e modulo non vanno messi nel messaggio |
| livello root | `INFO`, quindi il rientro dall'errore loggato a INFO e' visibile in produzione |
| destinazione | solo `StreamHandler` su stdout, cioe' i log del container |
| i componenti sono singleton? | si', uno per processo (`component/*/__init__.py`), tranne le tende che sono due istanze da `FactoryCurtain` |
| dove nascono gli stati | `get_status()` in roof, curtains, cover_mirror, button_control; il telescopio invece assegna `self.status` da piu' punti del suo loop |
| copertura attuale | cover_mirror completa, roof solo timeout, curtains **zero**, telescope solo `ERROR` con `exc_info` |

## 4. Prerequisiti e decisioni

- **Nessuna dipendenza nuova**, nessun altro repo.
- **Dove tenere lo stato precedente**: come attributo dell'istanza del componente, non in un
  registro globale di modulo. I componenti sono singleton in produzione, quindi il
  comportamento e' lo stesso, ma nei test ogni istanza parte pulita e non serve azzerare
  nulla fra un test e l'altro.
- **Livello del rientro**: `INFO`. Un guasto rientrato non e' un errore, ma senza quella riga
  dal log non si ricava quanto e' durato.
- **Cause da nominare** (prima stesura, da validare implementando):
  `device_unreachable`, `movement_not_confirmed`, `sensors_inconsistent`,
  `blocked_by_safety`, `state_not_recognized`.
- **Il telescopio e' il caso diverso**: `self.status` viene assegnato da piu' punti del loop.
  Intercettare le transizioni con una property setter cattura tutte le assegnazioni in un
  posto solo, comprese quelle dentro `retrieve()`. Va valutato durante l'implementazione se
  il refactor resta contenuto: se sporca troppo, si logga nei singoli punti.

## 5. Implementazione

Un helper unico, senza stato globale, e la sua chiamata nei punti dove lo stato di errore
nasce:

| dove | cosa |
|---|---|
| `component/roof/roof_control.py:55-56` | distinguere `sensors_inconsistent` (i due finecorsa attivi insieme) da `blocked_by_safety` (`is_blocked`), oggi indistinguibili |
| `component/curtains/curtains.py:157` | `CURTAIN_ERROR` e' il valore di partenza restituito per esclusione: causa `state_not_recognized`, oggi nessuna riga di log |
| `component/cover_mirror/cover_mirror_control.py` | i due `logger.error` gia' presenti diventano transizioni: stesso messaggio, ma una volta sola invece che a ogni polling |
| `component/telescope/telescope.py:170-171` e `indigo/telescope.py:319` | `ERROR` e `LOST` con la causa, mantenendo `exc_info` dove c'e' gia' |

Il prefisso `[CoverMirror]` diventa la convenzione per tutti: componente fra parentesi
quadre, poi la causa.

## 6. Strategia di test

### Automatici, con `assertLogs`

1. Transizione verso l'errore: **un** record `ERROR`, con componente e causa nel messaggio.
2. Stessa lettura ripetuta: **nessun** nuovo record (e' la dedup, il cuore della storia).
3. Rientro: record `INFO`, e una successiva lettura sana non produce altro.
4. Cambio di causa a parita' di stato di errore (roof: da `sensors_inconsistent` a
   `blocked_by_safety`): **nuovo** record, altrimenti si perde il passaggio da un guasto a un altro.
5. Per le tende, che oggi non loggano nulla, il test 1 e' rosso per assenza totale.

### Manuale, sul crac-test-stack

1. Precondizione: stack avviato e sano. Azione: `docker logs --since 60s | grep " - ERROR - "`.
   Atteso: nessuna riga - il caso normale non scrive.
2. Precondizione: stack avviato. Azione: scollegare il device della copertura da INDIGO,
   riavviare `crac-server`, attendere due cicli di polling. Atteso: **una** riga `ERROR` con
   `[CoverMirror]` e la causa, non una per ciclo.
3. Azione: ricollegare il device. Atteso: una riga `INFO` di rientro.

Il tetto e le tende sullo stack girano su GPIO mock: le loro transizioni si verificano solo
con i test automatici.
