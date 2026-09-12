# Blocchi di sicurezza: come reagisce CRaC a meteo e UPS

Stato al 8 settembre 2026 — repo `crac-server`.

Questo documento mette a confronto **come si comporta CRaC oggi** di fronte a
condizioni meteo o di alimentazione avverse, e **come dovrebbe comportarsi**
una volta lavorate le storie già aperte. Serve a rendere visibile in un colpo
d'occhio quali situazioni sono coperte e quali no.

"Oggi" è il codice di `main`: la PR #83, che chiude la issue #74, è stata
mergiata l'8 settembre 2026 con il commit `46b4536`.

## Le quattro condizioni

Sia il meteo sia l'UPS riportano uno di quattro stati:

| stato | significato |
|---|---|
| **normale** | i valori misurati sono dentro le soglie di sicurezza |
| **warning** | i valori sono oltre la soglia di attenzione ma non di pericolo |
| **pericoloso** | almeno un valore è oltre la soglia di pericolo |
| **sconosciuto** | non c'è un dato da valutare: stazione irraggiungibile, lettura più vecchia del consentito, device che non risponde |

Lo stato **sconosciuto** non è una via di mezzo fra normale e pericoloso: è
l'assenza di informazione. È la condizione trattata peggio oggi, ed è anche
quella che si presenta proprio quando il maltempo arriva — un blackout o una
raffica che stacca l'anemometro fanno sparire il dato nel momento in cui
serviva di più.

## Osservatorio fermo: si vuole aprire o accendere

| condizione | tetto | tende | telescopio | dopo le storie |
|---|---|---|---|---|
| meteo normale | permesso | permesso | permesso | invariato |
| meteo **warning** | permesso | permesso | permesso | **da decidere** (vedi nota 1) |
| meteo **pericoloso** | bloccato | bloccato | bloccato | invariato |
| meteo **sconosciuto** | bloccato ¹ | bloccato ¹ | **permesso** | tutti bloccati ¹ — issue #85 |
| UPS **pericoloso** | permesso | permesso | permesso | tetto e tende bloccati — issue #22; telescopio — issue #85 |
| UPS **sconosciuto** | permesso | permesso | permesso | tutti bloccati ¹ — issue #22 e #85 |

¹ Subordinato alla chiave `block_on_unspecified`, che decide se aprire quando
il dato non c'è. Esiste per il meteo, sarà introdotta per l'UPS dalla issue #22.

Prima della PR #83 la riga "meteo pericoloso" aveva il telescopio **permesso**:
l'accensione non veniva bloccata nemmeno con maltempo dichiarato.

## Osservatorio in funzione: tetto aperto, tende attive, telescopio acceso

| condizione | oggi | dopo le storie |
|---|---|---|
| meteo normale o warning | nessuna reazione | invariato |
| meteo **pericoloso** | chiusura immediata e completa | chiusura dopo un tempo di grazia, nell'ordine dei 5 minuti — **non ancora collocato in nessuna storia** |
| meteo **sconosciuto** | **nessuna reazione** | chiusura dopo attesa configurabile — issue #85 |
| UPS **pericoloso** | **nessuna reazione** | chiusura — issue #22: batteria critica subito, alimentazione degradata dopo `critical_time` |
| UPS **sconosciuto** | **nessuna reazione** | chiusura dopo attesa configurabile — issue #85 |

Quando la chiusura di emergenza parte, esegue in sequenza: park del telescopio,
attesa che sia in posizione, disabilitazione delle due tende, attesa che siano
ferme, chiusura del tetto, spegnimento del pulsante del telescopio.

**Vale per tutte le righe**: oggi nessuno di questi controlli viene valutato se
crac-cloud non interroga crac-server. È l'oggetto della issue #72, prerequisito
di tutto il resto.

## Perché il telescopio è l'anello debole

I controlli su tetto, tende e telescopio sono scritti in tre file separati, e
ogni fonte di pericolo va aggiunta a mano in ciascuno. Il risultato è che il
telescopio è oggi protetto in un caso su quattro, e la issue #22 così com'è
scritta lo lascerebbe scoperto anche dopo, perché nomina solo il tetto e le
tende.

Non è una decisione presa da qualcuno: è l'effetto di tre implementazioni
indipendenti. Lo stesso meccanismo aveva già prodotto il difetto corretto dalla
PR #83, dove il blocco del telescopio era presente ma disattivato.

## Note

**1. Il livello warning non blocca nulla, per una scelta del 2022 mai motivata.**
`WEATHER_STATUS_WARNING` viene calcolato in `weather_converter.py` ma non
compare in nessun altro punto del codice: nessun controllo lo legge.

Non è una dimenticanza. Il blocco sul warning era stato introdotto il
5 dicembre 2022 (commit `19dcd4f`, PR #30, *automatic closure for bad weather
conditions*) come `>= WEATHER_STATUS_WARNING` su tetto, tende e telescopio, e
rimosso il giorno dopo, il 6 dicembre 2022 (commit `18d560d`, PR #31), portando
la condizione a `== WEATHER_STATUS_DANGER` su tutti e tre insieme. La modifica è
coerente e regge da quattro anni.

Il punto è che non è motivata da nessuna parte: la PR #31 si intitola *the
asynchronous park should be used for moving the telescope in park position* e il
suo corpo è una riga. Il cambio di soglia è l'unica modifica sostanziale che quel
titolo non annuncia, insieme al park asincrono e a una pulizia di log. La
spiegazione più plausibile, visto il giorno di distanza, è che bloccare già sul
warning si fosse rivelato troppo restrittivo — ma resta una ricostruzione, non un
fatto documentato.

Oggi quindi il warning è un livello che esiste, viene calcolato e mostrato
all'operatore, ma non ha alcun effetto sul comportamento. Non è coperto da
nessuna storia aperta.

**2. La casella più esposta.**
"Meteo sconosciuto, osservatorio in funzione" è l'unica combinazione in cui non
succede nulla né all'accensione né dopo. Coincide con lo scenario in cui la
stazione tace perché il maltempo sta arrivando.

**3. Due attese da non confondere.**
La issue #22 prevede `critical_time = 300`, cinque minuti, per verificare che
una condizione di alimentazione degradata **persista** prima di reagire. È cosa
diversa dal tempo di grazia concesso all'operatore per completare le operazioni
in corso, e dall'attesa prima di reagire a un dato mancante. Se venissero
implementate senza distinguerle, si sommerebbero.

## Storie di riferimento

| storia | stato | oggetto |
|---|---|---|
| issue #74 | chiusa, PR #83 mergiata | blocco meteo mai attivato: chiave di configurazione assente e blocco del telescopio disattivato nel codice |
| PR #83 | mergiata in main (`46b4536`) | corregge la issue #74, più le soglie meteo incoerenti e la classificazione dei valori fuori scala |
| issue #85 | aperta, da lavorare | i controlli valutano solo l'accensione: a osservatorio aperto nessuno reagisce, e il telescopio è coperto a metà |
| issue #22 | aperta, da lavorare | chiusura automatica e blocco apertura per condizioni UPS critiche |
| issue #72 | aperta, da lavorare | crac-server deve valutare i controlli in autonomia, non solo quando li chiama crac-cloud |
| issue #82 | aperta, da lavorare | indicatore visivo quando un controllo di sicurezza è disattivato |
| issue #84 | aperta, decisione | unificare configurazione e costruzione dei grafici fra meteo e UPS |

Tutte nella milestone *Sicurezza e affidabilità*, tranne la issue #84 che è in
*Decisioni aperte*.
