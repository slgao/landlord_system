---
source_type: internal_doc
law_ref: null
title: "Vermio – wie die Nebenkostenabrechnung berechnet wird"
url: null
---

## Proration: tagesgenau, pro Kopf

Vermio berechnet die Nebenkostenabrechnung tagesgenau (day-based) und pro
Kopf (per-person), nicht pauschal pro Wohnung. Jede Kostenart (Strom, Gas,
Wasser, Heizung, sonstige Betriebskosten) kann entweder über Zählerstände
erfasst werden oder über einen direkten Gesamtbetrag, und kann mehrere
Abrechnungsperioden enthalten (z. B. eine Rechnung pro Jahr vom Versorger),
die einzeln ausgewiesen und am Ende zu einer Abrechnung summiert werden.

## WG-Awareness

Die Personenzahl-Logik ist WG-fähig: Vermio unterscheidet zwischen einem
gemeinsamen Vertrag für eine Wohngemeinschaft (Kostenanteil nach Kopfzahl der
gesamten WG) und einem Einzelvertrag pro Zimmer (jeder Vertrag zählt
unabhängig). Das ist wichtig, weil BetrKV keine Umlageschlüssel vorschreibt —
Wohnfläche, Personenzahl oder Verbrauch sind alle zulässig, solange der
Mietvertrag den Schlüssel festlegt oder (mangels Vereinbarung) §556a BGB
greift, der im Zweifel die Wohnfläche als Maßstab vorsieht.

## Individuelle Abrechnungszeiträume je Kostenart

Jede Betriebskosten-Position hat einen eigenen, editierbaren
"Lebenszeitraum" (living period) relativ zum Vertrag — z. B. wenn ein Mieter
mitten im Jahr eingezogen ist und der Versorgerzeitraum nicht exakt mit dem
Vertragsbeginn übereinstimmt. Das reduziert den häufigsten manuellen
Fehler bei Nebenkostenabrechnungen: falsch zugeordnete Zeiträume bei
Mieterwechsel.

## Verrechnung mit der Kaution

Ein offener Nachzahlungsbetrag aus der Nebenkostenabrechnung kann in Vermio
gegen eine noch gehaltene Kaution verrechnet werden (siehe BGB §551 zur
Kaution und BGB §556 zur Abrechnung) — das System zeigt den verbleibenden
Kautionssaldo nach Verrechnung.

## PDF-Ausgabe

Erzeugte Abrechnungs-PDFs enthalten die vollständige Anschrift des Mieters
(Straße, PLZ, Ort), den Abrechnungszeitraum und eine geschlechtsspezifische
Anrede (Herr/Frau), passend zur formalen Zustellungspflicht aus BGB §556
Abs. 3.
