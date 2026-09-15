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

## Technische Hinweise

- **Zeitzone**: Europe/Berlin (alle Zeiten)
- **Sprache**: Deutsch (UI), Englisch (Code/Dokumentation)
- **CDN**: Keine - alle Assets lokal
- **Passwort**: Aus `.env` - bitte sicher aufbewahren
