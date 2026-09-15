# Parking Cockpit - Betreibereinstellungen

## Übersicht

Parking Cockpit ist eine lokale Web-Anwendung zur Verwaltung von Parkplatz-Reservierungen. Das System ruft automatisch Reservierungs-E-Mails ab und zeigt sie in einem übersichtlichen Dashboard an.

## Erste Schritte

### Anmeldung

1. Öffnen Sie `http://127.0.0.1:8000` in Ihrem Browser
2. Geben Sie das Passwort aus der `.env`-Datei ein
3. Klicken Sie auf "Anmelden"

### Dashboard ("Aktuell auf dem Platz")

Zeigt alle aktuellen Reservierungen, deren Zeitfenster die aktuelle Zeit enthält.

- **Kennzeichen** prominent oben angezeigt
- **Name** des Kunden
- **Abfahrtszeit** in Rot
- **Anbieter-Badge** zeigt die Quelle (Kravag, Homepage, etc.)

### "Kommend" - Kommende Reservierungen

Zeigt alle Reservierungen der nächsten 7 Tage (konfigurierbar).

- Nach Tagen gruppiert
- Sortiert nach Ankunftszeit

### "Alle / Archiv"

Vollständige Übersicht aller Reservierungen.

**Filteroptionen:**
- Nach Anbieter filtern (Kravag, Trucks nB, SNAP, Homepage, Manuell)
- Nach Status filtern (Neu, Bestätigt, Storniert, Abgeschlossen)
- Freitextsuche nach Kennzeichen oder Name (fehlertolerant)

**Export:**
- CSV-Export für externe Auswertung

### Klärungsfälle

E-Mails, die nicht automatisch verarbeitet werden konnten, landen hier:

**Mögliche Gründe:**
- **Unbekannter Anbieter**: E-Mail von unbekannter Quelle
- **Parsing fehlgeschlagen**: E-Mail-Format konnte nicht erkannt werden
- **Unvollständige Daten**: Zeitfenster fehlt oder ist unvollständig
- **Verdacht auf Duplikat**: Mögliche Doppelbuchung

**Aktionen:**
- E-Mail-Inhalt anzeigen (klicken Sie auf "E-Mail anzeigen")
- Als erledigt markieren
- Manuell als Reservierung anlegen

## Reservierung bearbeiten

### Neue Reservierung anlegen

1. Klicken Sie auf "Alle / Archiv"
2. Klicken Sie auf "+ Neue Reservierung"
3. Füllen Sie das Formular aus:
   - **Anbieter**: Auswählen
   - **Kennzeichen**: Pflichtfeld
   - **Zeitfenster**: Von/Bis Datum und Uhrzeit
   - **Kundenname, E-Mail**: Optional

### Reservierung ändern

1. Klicken Sie auf eine Reservierung in einer Listen- oder Kartenansicht
2. Ändern Sie die gewünschten Felder
3. Klicken Sie auf "Speichern"

### Reservierung stornieren

1. Öffnen Sie die Reservierung
2. Ändern Sie den Status zu "Storniert"
3. Optional: Notiz hinzufügen
4. Speichern

### Reservierung löschen

1. Öffnen Sie die Reservierung
2. Klicken Sie auf "Löschen"
3. Bestätigen Sie die Löschung

**Hinweis**: Löschungen werden nicht rückgängig gemacht.

## Konfiguration

### IMAP-Einstellungen (.env)

```
IMAP_HOST=imap.ihre-domain.de
IMAP_PORT=993
IMAP_USER=parking@ihre-domain.de
IMAP_PASS=ihr-passwort
```

### Poll-Intervall (config.yaml)

Standard: Alle 5 Minuten. Anpassbar:

```yaml
polling:
  interval_minutes: 5  # Erhöhen für weniger häufiges Abrufen
```

### Dashboard-Einstellungen (config.yaml)

```yaml
ui:
  upcoming_days: 7              # Tage in "Kommend" anzeigen
  current_window_grace_minutes: 0  # Gnadenzeit in Minuten
  auto_refresh_seconds: 60     # Auto-Refresh (0 = aus)
```

## Fehlerbehebung

### Keine E-Mails werden abgerufen

1. Prüfen Sie die IMAP-Einstellungen in `.env`
2. Prüfen Sie die Logs auf Verbindungsfehler
3. Testen Sie die Verbindung manuell:
   ```bash
   python -m parking_cockpit poll-once
   ```

### Reservierung fehlt im Dashboard

- Prüfen Sie das Zeitfenster (von/bis)
- Prüfen Sie den Status (Stornierte werden nicht angezeigt)
- Prüfen Sie "Kommend" für zukünftige Reservierungen
- Prüfen Sie "Alle / Archiv" mit erweiterten Filtern

### Falsche Daten in Reservierung

- Bearbeiten Sie die Reservierung manuell
- Fügen Sie eine Notiz hinzu, z.B. "Korrektur: falsches Kennzeichen"

## Datenschutz

Alle Daten werden lokal gespeichert:

- **SQLite-Datenbank**: `parking_cockpit.db`
- **Roh-E-Mails**: `raw_mails/` Ordner (365 Tage Aufbewahrung)
- **Keine Cloud-Dienste**: 100% lokale Verarbeitung
- **Keine externen Anfragen**: Außer IMAP-Server

## Support

Bei Problemen:

1. Prüfen Sie die Log-Datei (`parking_cockpit.log`)
2. Führen Sie `python -m parking_cockpit status` aus
3. Kontaktieren Sie den Systemadministrator

## Platzkarte

Die Platzkarte zeigt eine interaktive Übersicht aller Parkplätze und ermöglicht die manuelle Zuweisung von Fahrzeugen zu Plätzen.

### Zugriff

- **Eigenständige Seite**: Klicken Sie im Header auf "Platzkarte"
- **Eingebettet**: Auf dem Dashboard unter "Aktuell auf dem Platz" finden Sie eine Miniatur-Ansicht

### Farblegende

| Farbe | Bedeutung |
|-------|-----------|
| 🟢 Grün | Frei – kein Fahrzeug zugewiesen |
| 🔴 Rot | Belegt – aktives Fahrzeug zugewiesen |
| 🟡 Gelb | Gesperrt – Platz nicht verfügbar |
| 🔴🟡 Gestreift | Belegt + Gesperrt – Warnung! |
| 🩷 Rosa umrandet | Frauenparkplatz (Belegungsfarben gelten trotzdem) |

### Live-Zähler

Oben der Karte sehen Sie vier Zähler:
- **X frei** – verfügbare Plätze
- **Y belegt** – aktuell zugewiesene Fahrzeuge
- **Z gesperrt** – temporär gesperrte Plätze
- **W ohne Platz** – aktive Reservierungen OHNE Platz Zuweisung

### Arbeitsablauf: Platz zuweisen

1. **Platz anklicken** – öffnet das Seitenpanel
2. **Bei freiem Platz**: Wählen Sie aus der Liste "Fahrzeug setzen":
   - ⚡ **Ohne Platz** – Reservierungen ohne Platz (zuerst angezeigt)
   - 🔄 **Auf anderem Platz** – Fahrzeuge die umgesetzt werden sollen
3. **Klicken Sie auf ein Fahrzeug** – es wird sofort diesem Platz zugewiesen
4. Das Fahrzeug wird automatisch vom alten Platz entfernt (Umsetzen)

### Walk-in erfassen

Für spontane arrivals ohne Reservierung:

1. Freien Platz anklicken
2. Button "+ Walk-in" klicken
3. Kennzeichen eingeben (Pflicht)
4. Optional: Abfahrtszeit (HH:MM)
5. "Erfassen" – erstellt MANUAL-Reservierung und weist Platz zu

### Platz sperren/entsperren

**Sperren:**
1. Platz anklicken (frei oder belegt)
2. Sperrgrund eingeben
3. 🔒 Button klicken

**Entsperren:**
1. Gesperrten Platz anklicken
2. "✓ Entsperren" klicken

### Fahrzeug wechseln

Bei belegtem Platz:
- **"Fahrzeug wechseln"** – öffnet gleiche Picker-Liste wie bei freien Plätzen
- Altes Fahrzeug wird automatisch freigegeben

### Frei melden vs. Checkout

- **Frei melden** – Platz wird frei, Reservierung bleibt erhalten (Status unverändert)
- **Checkout** – Platz wird frei, Reservierung setzt Status auf DONE (abgeschlossen)

### Auto-Place Funktion

Button oben rechts: **"🚍 Auto (X)"** – verteilt alle unzugewiesenen Reservierungen:
- TRUCK → erster freier TRUCK-Platz
- CAR → erster freier CAR-Platz
- WOMEN-Parkplätze werden NIEMALS automatisch belegt
- Jede Zuweisung erhält Notiz: "automatisch zugewiesen"

**Einstellung**: `assignment.auto_assign: false` (Standard) verhindert automatische Zuweisung beim Aktivwerden einer Reservierung.

### spots.yaml bearbeiten

Die Platzgeometrie wird in `spots.yaml` definiert:

```yaml
spots:
- spot_number: W1
  row_label: W
  spot_type: WOMEN      # TRUCK | CAR | WOMEN
  x: 10                 # Prozent X (0-100)
  y: 38                 # Prozent Y (0-100)
  width: 7              # Prozent Breite
  height: 4             # Prozent Höhe
  rotation: 0           # Grad Drehung
```

Nach Änderungen:
```bash
python -m app.cli spots-reload
```

**Wichtig**: Bestehende Sperrungen und Zuweisungen bleiben erhalten!

### Modi

- **Schema-Modus** – saubere schematische Darstellung mit Raster
- **Foto-Modus** – verwendet Luftbild unter `app/web/static/lot.jpg`

Umschalten über Dropdown oben oder Config `ui.map_background: "schema"|"foto"`

## Technische Hinweise

- **Zeitzone**: Europe/Berlin (alle Zeiten)
- **Sprache**: Deutsch (UI), Englisch (Code/Dokumentation)
- **CDN**: Keine - alle Assets lokal
- **Passwort**: Aus `.env` - bitte sicher aufbewahren
