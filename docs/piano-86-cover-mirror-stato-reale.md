# Piano — #86 Copertura specchio: il pulsante non riflette lo stato reale

Branch: `fix/86-cover-mirror-real-state` (da `main` @ `46b4536`).
Issue: https://github.com/ara-astronomia/crac-server/issues/86

## 0. Come riprendere

Il branch **esiste gia'**, creato da `main` @ `46b4536`. Nessun file di codice
e' stato ancora toccato: il lavoro parte dai test.

```bash
cd ../crac-server
git checkout fix/86-cover-mirror-real-state
uv run python -m unittest discover -s tests     # baseline attesa: 156 test, OK
```

Il codice da modificare e' un solo file, `crac_server/component/cover_mirror/cover_mirror_control.py`,
funzione `get_status()` (sezione 5). I test da scrivere per primi stanno in
`tests/component/cover_mirror/test_cover_mirror_control.py` (sezione 6).

**Una decisione e' ancora aperta** e va confermata prima di implementare: cosa
riportare quando la proprieta' INDIGO arriva senza `state` (sezione 4).

## 1. Cosa dice l'issue (e cosa e' emerso investigando)

In produzione il pulsante dei petali diventa verde anche quando i petali non si
muovono. Il caso osservato: alimentatore spento, petali fermi, pulsante verde.

La catena verificata:

- il driver `RC_Cover` **segnala gia' il fallimento**: `indigo_rc_cover.c:130-143`
  mette `AUX_COVER` in `BUSY`, aspetta il feedback `ST_OPEN`/`ST_CLOSED`
  dall'ESP32 e senza conferma porta la proprieta' in `ALERT`
- `indigo_client` conserva in cache il vector INDIGO **intero**, `state` compreso
- `cover_mirror_control.get_status()` legge solo il valore degli item e **ignora
  lo `state`**: il valore dello switch dice cosa e' stato comandato, non cosa e'
  successo

### Scoperta che restringe il lavoro

L'issue inizialmente ipotizzava di dover aggiungere un `GetStatus` al servizio.
**Non serve**, il canale di rilettura esiste gia':

| pezzo | dove | stato |
|---|---|---|
| azione di sola lettura | `CHECK_COVER_MIRROR` nel proto | esiste, non fa muovere nulla |
| endpoint | `cover_mirror_router.py:28` | esiste, usa `SetAction(CHECK)` |
| polling | `coordinator.js:38` | esiste, ogni **3 secondi** |
| etichette UI | `buttons.js` | esistono per OPENING, CLOSING, ERROR |
| pulsante disabilitato in movimento | `CoverMirrorHandler` | esiste |

Tutto e' gia' al suo posto e aspetta stati che `get_status()` non produce mai.
`COVER_MIRROR_ERROR` e' oggi irraggiungibile se non quando la proprieta' manca
del tutto; `OPENING`/`CLOSING` non vengono mai prodotti.

**Il lavoro e' quindi tutto in una funzione.** Nessuna modifica a crac-protobuf,
crac-cloud o al frontend.

## 2. Ambiente di esecuzione

- **uv nativo**: `uv run python -m unittest discover -s tests`.
- **Baseline verificata: 156 test, OK** su `main` @ `46b4536`.
- Il `crac-test-stack` serve per la verifica manuale, con il limite della
  sezione 4.

## 3. Verifiche eseguite

| verifica | risultato |
|---|---|
| il driver reale segnala l'esito? | si', `BUSY` durante il movimento, `ALERT` senza feedback |
| lo `state` arriva a crac-server? | si', `_merge_property` conserva il vector intero |
| `get_status()` lo legge? | no, guarda solo `switch.get("value")` |
| serve un `GetStatus` nuovo? | no, `CHECK_COVER_MIRROR` + polling a 3s esistono gia' |
| test esistenti sulla copertura | si', `tests/component/cover_mirror/test_cover_mirror_control.py`, 8 test |
| le fixture dei test hanno lo `state`? | no, usano proprieta' senza `state` |

## 4. Prerequisiti e decisioni

- **Nessuna dipendenza nuova, nessun repo oltre crac-server.**
- **Decisione da prendere**: cosa fare quando `state` manca dalla proprieta'.
  INDIGO lo manda sempre, quindi e' un caso teorico, ma la scelta prudente e'
  `COVER_MIRROR_ERROR`: senza esito non si puo' affermare che sia aperto.
  Comporta aggiornare le fixture di due test esistenti, che oggi passano
  proprieta' senza `state`.
- **Limite del test manuale**: il simulatore usato dal test-stack
  (`indigo_rc_cover_simulator.c`) imposta **sempre** `INDIGO_OK_STATE`, quindi
  sullo stack non e' riproducibile ne' `BUSY` ne' `ALERT`. Sullo stack si puo'
  verificare solo che il caso `Ok` continui a funzionare come prima. Riprodurre
  il fallimento richiederebbe di estendere il simulatore in `RC_Cover`, che e'
  lavoro su un altro repo: da valutare a parte, e' utile ma non necessario per
  chiudere questa storia.

## 5. Implementazione

Unico file: `crac_server/component/cover_mirror/cover_mirror_control.py`,
funzione `get_status()`.

Leggere `prop.get("state")` prima di guardare gli item:

| `state` INDIGO | stato riportato |
|---|---|
| `Busy` | `COVER_MIRROR_OPENING` o `COVER_MIRROR_CLOSING`, secondo lo switch a `true` |
| `Alert` | `COVER_MIRROR_ERROR` |
| `Ok` | `COVER_MIRROR_OPENED` / `COVER_MIRROR_CLOSED` come oggi |
| assente | `COVER_MIRROR_ERROR` (vedi decisione in sezione 4) |

Il resto della catena non si tocca: gli stati nuovi sono gia' gestiti da
`CoverMirrorHandler` e da `CoverMirrorConverter`.

## 6. Strategia di test

Suite disponibile: si procede in TDD, rosso prima.

### Automatici, in `tests/component/cover_mirror/test_cover_mirror_control.py`

1. `state` `Alert` con `OPEN` a true → `COVER_MIRROR_ERROR`, **non** `OPENED`.
   E' il caso osservato in produzione: il test che riproduce il difetto.
2. `state` `Busy` con `OPEN` a true → `COVER_MIRROR_OPENING`; con `CLOSE` a true
   → `COVER_MIRROR_CLOSING`.
3. `state` `Ok` → `OPENED`/`CLOSED`, cioe' il comportamento attuale preservato.
4. `state` assente → `COVER_MIRROR_ERROR`.
5. Aggiornare le fixture dei due test esistenti che oggi omettono `state`.

Verificare che i test mordano: rimettendo la vecchia `get_status()` deve
fallire almeno il test 1.

### Manuale, sul crac-test-stack

Limitato al caso `Ok`, per il motivo in sezione 4:

1. `docker compose up -d`, copertura chiusa.
   **Atteso**: pulsante rosso, etichetta "Chiuso".
2. Premere il pulsante di apertura.
   **Atteso**: entro un ciclo di polling (3 s) il pulsante diventa verde con
   etichetta "Aperto". Nessuna regressione rispetto a oggi.
3. Premere di nuovo per chiudere.
   **Atteso**: torna rosso, "Chiuso".

Il caso che ha originato la storia - `ALERT` con petali fermi - **non e'
riproducibile sullo stack** e resta coperto solo dai test automatici. Da dire
esplicitamente in fase di review, senza spacciare la verifica come completa.
