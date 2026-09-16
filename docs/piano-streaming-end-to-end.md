# Piano: streaming end-to-end (polling → push)

Spike di riferimento: ara-astronomia/crac-server#51

## Milestone (una per repo, GitHub non supporta milestone di organizzazione)

- crac-server: https://github.com/ara-astronomia/crac-server/milestone/1
- crac-protobuf: https://github.com/ara-astronomia/crac-protobuf/milestone/1
- crac-cloud: https://github.com/ara-astronomia/crac-cloud/milestone/1

Vista aggregata cross-repo: le 10 storie sono state aggiunte al Project (v2)
di organizzazione già esistente "Crac" (https://github.com/orgs/ara-astronomia/projects/1),
che raccoglie issue da tutti i repo del progetto - non ne è stato creato uno nuovo
per non frammentare la vista.

## Storie (ordine di dipendenza)

1. crac-server#52 - Meccanismo di callback/osservatore su IndigoClient
2. crac-server#53 - Telescope/CoverMirrorControl: ricalcolo event-driven (sostituisce il timer, non lo affianca)
3. crac-protobuf#19 - Nuove RPC server-streaming per lo stato (affiancate alle unarie)
4. crac-server#54 - Implementare le RPC streaming sul core event-driven
5. crac-cloud#5 - Client gRPC streaming verso crac-server
6. crac-cloud#6 - Endpoint WebSocket verso il browser
7. crac-cloud#7 - Frontend: sostituire il polling JS con client WebSocket
8. crac-cloud#8 - Pulizia: rimuovere gli endpoint HTTP GET di stato a polling
9. crac-protobuf#20 - Pulizia: rimuovere le RPC unarie di stato legacy
10. crac-server#55 / crac-cloud#9 / crac-protobuf#21 - Aggiornare CLAUDE.md (una per repo)

## Principio guida

Le chiamate azione (connect/disconnect/park/flat/sync/enable/disable/open/close)
restano sempre unarie/POST - sono comandi puntuali, non stato continuo. Solo il
percorso di lettura dello stato passa da polling a streaming.

## Coordinamento con issue esistenti

- crac-server#48 (autolight) e crac-server#50 (nome device da INDIGO) fanno
  riferimento al ciclo di polling attuale nei loro fix proposti - annotato con
  un commento su entrambe: se lavorate prima di questa migrazione, vanno
  riadattate al nuovo meccanismo a callback (#52) invece che al timer che sparisce.
