"""Web routes for Parking Cockpit."""

import csv
import io
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo
from pathlib import Path

from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.config import get_settings, get_configured_timezone, get_base_dir
from app.db import get_db, init_db
from app.models import Reservation, ReservationStatus, QueueReason
from app.repositories import ReservationRepository, MailLogRepository, ParseQueueRepository, ParkingSpotRepository
from app.parsers import normalize_license_plate

# Create FastAPI app
app = FastAPI(title="Parking Cockpit")

# Session middleware
app.add_middleware(
    SessionMiddleware,
    secret_key="parking-cockpit-secret-key-123",
    
    
)

# Mount static files
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Timezone
tz = ZoneInfo(get_configured_timezone())
settings, _, _, ui_settings, _ = get_settings()


def get_current_time() -> str:
    """Get current time formatted for display."""
    return datetime.now(tz).strftime("%d.%m.%Y %H:%M")


def require_auth(request: Request) -> bool:
    """Check if user is authenticated."""
    password = request.session.get("authenticated")
    return password == ui_settings.password


@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    init_db()


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Show login page."""
    if require_auth(request):
        return RedirectResponse(url="/", status_code=303)
    
    base_path = Path(__file__).parent / "templates"
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    
    env = Environment(
        loader=FileSystemLoader(str(base_path)),
        autoescape=select_autoescape(['html', 'xml'])
    )
    
    template = env.get_template("login.html")
    
    context = {
        "request": request,
        "auto_refresh": None,
        "queue_count": 0,
        "current_time": get_current_time(),
    }
    
    return HTMLResponse(template.render(**context))


@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    """Process login."""
    if password == ui_settings.password:
        request.session["authenticated"] = password
        return RedirectResponse(url="/", status_code=303)
    
    base_path = Path(__file__).parent / "templates"
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    
    env = Environment(
        loader=FileSystemLoader(str(base_path)),
        autoescape=select_autoescape(['html', 'xml'])
    )
    
    template = env.get_template("login.html")
    context = {
        "request": request,
        "auto_refresh": None,
        "queue_count": 0,
        "current_time": get_current_time(),
    }
    
    return HTMLResponse(template.render(**context, error="Falsches Passwort"))


@app.get("/logout")
async def logout(request: Request):
    """Process logout."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


def render_template(template_name: str, request: Request, context: dict):
    """Render a Jinja2 template with common context."""
    base_path = Path(__file__).parent / "templates"
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    
    env = Environment(
        loader=FileSystemLoader(str(base_path)),
        autoescape=select_autoescape(['html', 'xml'])
    )
    
    context.update({
        "request": request,
        "auto_refresh": settings.ui.auto_refresh_seconds if settings.ui.auto_refresh_seconds > 0 else None,
        "queue_count": context.get("queue_count", 0),
        "current_time": get_current_time(),
    })
    
    template = env.get_template(template_name)
    return HTMLResponse(template.render(**context))


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """Dashboard showing current reservations."""
    if not require_auth(request):
        return RedirectResponse(url="/login", status_code=303)
    
    reservation_repo = ReservationRepository(db)
    queue_repo = ParseQueueRepository(db)
    
    reservations = reservation_repo.find_current(
        grace_minutes=settings.ui.current_window_grace_minutes
    )
    
    arriving_today = len(reservation_repo.find_arriving_today())
    queue_count = queue_repo.get_unresolved_count()

    try:
        map_ctx = build_map_context(db)
    except Exception:
        map_ctx = {"spots": [], "counters": {"free": 0, "occupied": 0, "closed": 0, "no_spot": 0},
                   "map_mode": "schema", "has_photo": False}

    return render_template("dashboard.html", request, {
        "reservations": reservations,
        "stats": {
            "current": len(reservations),
            "arriving_today": arriving_today,
            "queue": queue_count
        },
        "spots": map_ctx["spots"],
        "counters": map_ctx["counters"],
        "map_mode": map_ctx["map_mode"],
        "has_photo": map_ctx["has_photo"],
        "queue_count": queue_count,
        "grace_minutes": settings.ui.current_window_grace_minutes
    })


@app.get("/kommend", response_class=HTMLResponse)
async def kommend(request: Request, db: Session = Depends(get_db)):
    """Show upcoming reservations."""
    if not require_auth(request):
        return RedirectResponse(url="/login", status_code=303)
    
    reservation_repo = ReservationRepository(db)
    queue_repo = ParseQueueRepository(db)
    
    upcoming = reservation_repo.find_upcoming(days=settings.ui.upcoming_days)
    queue_count = queue_repo.get_unresolved_count()
    
    from collections import OrderedDict
    grouped = OrderedDict()
    for res in upcoming:
        if res.valid_from:
            day_key = res.valid_from.strftime("%A, %d. %B %Y")
            german_days = {
                "Monday": "Montag", "Tuesday": "Dienstag", "Wednesday": "Mittwoch",
                "Thursday": "Donnerstag", "Friday": "Freitag", "Saturday": "Samstag", "Sunday": "Sonntag"
            }
            german_months = {
                "January": "Januar", "February": "Februar", "March": "März",
                "April": "April", "May": "Mai", "June": "Juni",
                "July": "Juli", "August": "August", "September": "September",
                "October": "Oktober", "November": "November", "December": "Dezember"
            }
            for eng, ger in german_days.items():
                day_key = day_key.replace(eng, ger)
            for eng, ger in german_months.items():
                day_key = day_key.replace(eng, ger)
            
            if day_key not in grouped:
                grouped[day_key] = []
            grouped[day_key].append(res)
    
    return render_template("kommend.html", request, {
        "grouped": grouped,
        "days": settings.ui.upcoming_days,
        "queue_count": queue_count
    })


@app.get("/archiv", response_class=HTMLResponse)
async def archiv(
    request: Request,
    provider: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    db: Session = Depends(get_db)
):
    """Archive with filters and pagination."""
    if not require_auth(request):
        return RedirectResponse(url="/login", status_code=303)
    
    reservation_repo = ReservationRepository(db)
    queue_repo = ParseQueueRepository(db)
    
    reservations, total = reservation_repo.find_all(
        provider=provider,
        status=status,
        search_text=search,
        page=page,
        per_page=settings.ui.items_per_page
    )
    
    total_pages = (total + settings.ui.items_per_page - 1) // settings.ui.items_per_page
    queue_count = queue_repo.get_unresolved_count()
    
    return render_template("archiv.html", request, {
        "reservations": reservations,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "filters": {
            "provider": provider or "",
            "status": status or "",
            "search": search or ""
        },
        "queue_count": queue_count
    })


@app.get("/archiv/export", response_class=Response)
async def export_csv(
    request: Request,
    provider: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Export filtered reservations as CSV."""
    if not require_auth(request):
        return RedirectResponse(url="/login", status_code=303)
    
    reservation_repo = ReservationRepository(db)
    
    reservations, _ = reservation_repo.find_all(
        provider=provider,
        status=status,
        search_text=search,
        page=1,
        per_page=10000
    )
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        "ID", "Kennzeichen", "Normalisiert", "Vorname", "Nachname", "E-Mail",
        "Anbieter", "Von", "Bis", "Status", "Gutschein", "Unvollständig"
    ])
    
    for res in reservations:
        writer.writerow([
            res.id,
            res.plate_raw or "",
            res.plate_normalized or "",
            res.first_name or "",
            res.last_name or "",
            res.email or "",
            res.provider,
            res.valid_from.isoformat() if res.valid_from else "",
            res.valid_until.isoformat() if res.valid_until else "",
            res.status,
            res.voucher_code or "",
            "Ja" if res.incomplete_flag else "Nein"
        ])
    
    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=reservierungen_{datetime.now(tz).strftime('%Y%m%d')}.csv"
        }
    )


@app.get("/klärungsfälle", response_class=HTMLResponse)
async def klaerungsfaelle(request: Request, db: Session = Depends(get_db)):
    """Show clarification queue."""
    if not require_auth(request):
        return RedirectResponse(url="/login", status_code=303)
    
    queue_repo = ParseQueueRepository(db)
    queue = queue_repo.get_unresolved()
    
    return render_template("klaerungsfaelle.html", request, {
        "queue": queue,
        "queue_count": len(queue)
    })


@app.get("/klärungsfälle/mail/{queue_id}")
async def get_queue_mail(request: Request, queue_id: int, db: Session = Depends(get_db)):
    """Get mail content for a queue item."""
    if not require_auth(request):
        raise HTTPException(status_code=401)
    
    queue_repo = ParseQueueRepository(db)
    from app.models import ParseQueue
    
    item = db.query(ParseQueue).filter(ParseQueue.id == queue_id).first()
    if not item or not item.raw_mail_path:
        return Response(content="Keine E-Mail vorhanden", media_type="text/plain")
    
    try:
        with open(item.raw_mail_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return Response(content=content, media_type="text/plain")
    except Exception as e:
        return Response(content=f"Fehler beim Laden: {e}", media_type="text/plain")


@app.post("/klärungsfälle/{queue_id}/erledigen")
async def resolve_queue_item(
    request: Request,
    queue_id: int,
    note: str = Form(None),
    db: Session = Depends(get_db)
):
    """Mark a queue item as resolved."""
    if not require_auth(request):
        return RedirectResponse(url="/login", status_code=303)
    
    queue_repo = ParseQueueRepository(db)
    queue_repo.resolve(queue_id, note)
    db.commit()
    
    return RedirectResponse(url="/klärungsfälle", status_code=303)


@app.get("/reservierung/{reservation_id}", response_class=HTMLResponse)
async def reservation_detail(
    request: Request,
    reservation_id: str,
    db: Session = Depends(get_db)
):
    """Show reservation detail/edit form."""
    if not require_auth(request):
        return RedirectResponse(url="/login", status_code=303)
    
    queue_repo = ParseQueueRepository(db)
    
    if reservation_id == "Neu":
        return render_template("reservation_form.html", request, {
            "reservation": None,
            "audit_log": [],
            "queue_count": queue_repo.get_unresolved_count()
        })
    
    try:
        reservation_id = int(reservation_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid reservation ID")
    
    reservation_repo = ReservationRepository(db)
    reservation = reservation_repo.get_by_id(reservation_id)
    
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    
    return render_template("reservation_form.html", request, {
        "reservation": reservation,
        "audit_log": [],
        "queue_count": queue_repo.get_unresolved_count()
    })


@app.post("/reservierung/{reservation_id}")
async def save_reservation(
    request: Request,
    reservation_id: str,
    provider: str = Form(...),
    status: str = Form(...),
    plate_raw: str = Form(...),
    voucher_code: Optional[str] = Form(None),
    first_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    external_reservation_id: Optional[str] = Form(None),
    valid_from_date: Optional[str] = Form(None),
    valid_from_time: Optional[str] = Form(None),
    valid_until_date: Optional[str] = Form(None),
    valid_until_time: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Save reservation (create or update)."""
    if not require_auth(request):
        return RedirectResponse(url="/login", status_code=303)
    
    reservation_repo = ReservationRepository(db)
    
    valid_from = None
    valid_until = None
    
    if valid_from_date:
        try:
            if valid_from_time:
                valid_from = datetime.strptime(f"{valid_from_date} {valid_from_time}", "%Y-%m-%d %H:%M")
            else:
                valid_from = datetime.strptime(valid_from_date, "%Y-%m-%d")
            valid_from = valid_from.replace(tzinfo=tz)
        except ValueError:
            pass
    
    if valid_until_date:
        try:
            if valid_until_time:
                valid_until = datetime.strptime(f"{valid_until_date} {valid_until_time}", "%Y-%m-%d %H:%M")
            else:
                valid_until = datetime.strptime(valid_until_date, "%Y-%m-%d")
            valid_until = valid_until.replace(tzinfo=tz)
        except ValueError:
            pass
    
    if reservation_id == "Neu":
        from app.parsers import ParsedReservation
        parsed = ParsedReservation(
            provider=provider,
            first_name=first_name,
            last_name=last_name,
            email=email,
            plate_raw=plate_raw,
            plate_normalized=normalize_license_plate(plate_raw),
            valid_from=valid_from,
            valid_until=valid_until,
            voucher_code=voucher_code,
            external_reservation_id=external_reservation_id,
            status=status,
            notes=notes
        )
        reservation = reservation_repo.create(parsed)
    else:
        reservation_id = int(reservation_id)
        reservation = reservation_repo.get_by_id(reservation_id)
        if reservation:
            reservation.provider = provider
            reservation.status = status
            reservation.plate_raw = plate_raw
            reservation.plate_normalized = normalize_license_plate(plate_raw)
            reservation.voucher_code = voucher_code
            reservation.first_name = first_name
            reservation.last_name = last_name
            reservation.email = email
            reservation.external_reservation_id = external_reservation_id
            reservation.valid_from = valid_from
            reservation.valid_until = valid_until
            reservation.notes = notes
            reservation.updated_at = datetime.now(tz)
            db.flush()
    
    db.commit()
    
    return RedirectResponse(url=f"/reservierung/{reservation.id}", status_code=303)


@app.get("/reservierung/{reservation_id}/löschen")
async def delete_reservation(
    request: Request,
    reservation_id: int,
    db: Session = Depends(get_db)
):
    """Delete a reservation."""
    if not require_auth(request):
        return RedirectResponse(url="/login", status_code=303)
    
    reservation_repo = ReservationRepository(db)
    reservation_repo.delete(reservation_id)
    db.commit()
    
    return RedirectResponse(url="/archiv", status_code=303)


# =============================================================================
# Platzkarte (Parking Map) Routes
# =============================================================================

def build_map_context(db: Session) -> dict:
    """Build shared map context (spots with occupancy + counters)."""
    spot_repo = ParkingSpotRepository(db)
    reservation_repo = ReservationRepository(db)

    all_spots = spot_repo.get_all()
    spots_data = []
    for spot in all_spots:
        active_res = reservation_repo.find_active_on_spot(spot.id)
        spots_data.append({
            "id": spot.id,
            "spot_number": spot.spot_number,
            "row_label": spot.row_label,
            "spot_type": spot.spot_type,
            "x": spot.x,
            "y": spot.y,
            "width": spot.width,
            "height": spot.height,
            "rotation": spot.rotation,
            "is_closed": spot.is_closed,
            "closed_reason": spot.closed_reason,
            "reservation": active_res,
        })

    counters = spot_repo.count_by_status()
    counters["no_spot"] = len(reservation_repo.find_active_without_spot())

    base_dir = get_base_dir()
    has_photo = (base_dir / "app" / "web" / "static" / "lot.jpg").exists()

    return {
        "spots": spots_data,
        "counters": counters,
        "map_mode": settings.ui.map_background or "schema",
        "has_photo": has_photo,
    }


@app.get("/karte", response_class=HTMLResponse)
async def karte_page(
    request: Request,
    spot_id: Optional[int] = None,
    mode: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Show the interactive parking lot map."""
    if not require_auth(request):
        return RedirectResponse(url="/login", status_code=303)

    spot_repo = ParkingSpotRepository(db)
    reservation_repo = ReservationRepository(db)
    queue_repo = ParseQueueRepository(db)

    map_ctx = build_map_context(db)
    spots_data = map_ctx["spots"]

    selected_spot = None
    if spot_id:
        for s in spots_data:
            if s["id"] == spot_id:
                selected_spot = s
                break

    # Picker: active reservations on OTHER spots (move semantics)
    other_spot_reservations = []
    for res in reservation_repo.find_active_with_spot():
        if res.spot_id != spot_id:
            other_spot = spot_repo.get_by_id(res.spot_id)
            other_spot_reservations.append({
                "id": res.id,
                "plate_raw": res.plate_raw or "—",
                "first_name": res.first_name or "",
                "last_name": res.last_name or "",
                "provider": res.provider,
                "valid_until": res.valid_until,
                "spot": other_spot,
            })

    unassigned_reservations = []
    for res in reservation_repo.find_active_without_spot():
        unassigned_reservations.append({
            "id": res.id,
            "plate_raw": res.plate_raw or "—",
            "first_name": res.first_name or "",
            "last_name": res.last_name or "",
            "provider": res.provider,
            "valid_until": res.valid_until,
        })

    map_mode = mode or map_ctx["map_mode"]
    now = datetime.now(tz)

    return render_template("karte.html", request, {
        "spots": spots_data,
        "counters": map_ctx["counters"],
        "selected_spot": selected_spot,
        "unassigned_reservations": unassigned_reservations,
        "other_spot_reservations": other_spot_reservations,
        "map_mode": map_mode,
        "has_photo": map_ctx["has_photo"],
        "now_date": now.strftime("%d.%m."),
        "queue_count": queue_repo.get_unresolved_count(),
    })


@app.post("/spots/{spot_id}/assign")
async def spot_assign(
    request: Request,
    spot_id: int,
    reservation_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """Assign a reservation to a spot."""
    if not require_auth(request):
        return RedirectResponse(url="/login", status_code=303)

    reservation_repo = ReservationRepository(db)
    spot_repo = ParkingSpotRepository(db)

    spot = spot_repo.get_by_id(spot_id)
    reservation = reservation_repo.get_by_id(reservation_id)
    if reservation and spot:
        # Move semantics: reservation.spot_id simply points to the new spot;
        # the old spot becomes free automatically.
        reservation_repo.assign_to_spot(
            reservation_id, spot_id,
            f"Manuell zugewiesen zu Platz {spot.spot_number}"
        )
        db.commit()

    return RedirectResponse(url=f"/karte?spot_id={spot_id}", status_code=303)


@app.post("/spots/{spot_id}/release")
async def spot_release(
    request: Request,
    spot_id: int,
    mode: str = Form(...),
    db: Session = Depends(get_db)
):
    """Release a spot ('free' keeps reservation, 'checkout' sets status DONE)."""
    if not require_auth(request):
        return RedirectResponse(url="/login", status_code=303)

    reservation_repo = ReservationRepository(db)
    spot_repo = ParkingSpotRepository(db)

    active_res = reservation_repo.find_active_on_spot(spot_id)
    if active_res:
        spot = spot_repo.get_by_id(spot_id)
        spot_number = spot.spot_number if spot else str(spot_id)
        if mode == "checkout":
            reservation_repo.release_from_spot(active_res.id)
            reservation_repo.update_status(active_res.id, "DONE", f"Checkout von Platz {spot_number}")
        else:
            reservation_repo.release_from_spot(active_res.id)
            reservation_repo.update_status(active_res.id, active_res.status, f"Von Platz {spot_number} freigemeldet")

    db.commit()
    return RedirectResponse(url=f"/karte?spot_id={spot_id}", status_code=303)


@app.post("/spots/{spot_id}/close")
async def spot_close(
    request: Request,
    spot_id: int,
    reason: str = Form(...),
    db: Session = Depends(get_db)
):
    """Close/sperren a spot."""
    if not require_auth(request):
        return RedirectResponse(url="/login", status_code=303)

    spot_repo = ParkingSpotRepository(db)
    spot_repo.close_spot(spot_id, reason)
    db.commit()
    return RedirectResponse(url=f"/karte?spot_id={spot_id}", status_code=303)


@app.post("/spots/{spot_id}/open")
async def spot_open(
    request: Request,
    spot_id: int,
    db: Session = Depends(get_db)
):
    """Open/entsperren a spot."""
    if not require_auth(request):
        return RedirectResponse(url="/login", status_code=303)

    spot_repo = ParkingSpotRepository(db)
    spot_repo.open_spot(spot_id)
    db.commit()
    return RedirectResponse(url=f"/karte?spot_id={spot_id}", status_code=303)


@app.post("/spots/{spot_id}/walkin")
async def spot_walkin(
    request: Request,
    spot_id: int,
    plate: str = Form(...),
    until: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Create a walk-in (MANUAL) reservation and assign it to the spot."""
    if not require_auth(request):
        return RedirectResponse(url="/login", status_code=303)

    from app.parsers import ParsedReservation

    reservation_repo = ReservationRepository(db)
    spot_repo = ParkingSpotRepository(db)

    spot = spot_repo.get_by_id(spot_id)
    spot_number = spot.spot_number if spot else str(spot_id)

    now = datetime.now(tz)
    valid_from = now
    valid_until = now + timedelta(hours=2)

    if until:
        try:
            h, m = map(int, until.strip().split(":"))
            candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            valid_until = candidate
        except (ValueError, TypeError):
            pass

    parsed = ParsedReservation(
        provider="MANUAL",
        plate_raw=plate,
        plate_normalized=normalize_license_plate(plate),
        valid_from=valid_from,
        valid_until=valid_until,
        status="CONFIRMED",
    )
    reservation = reservation_repo.create(parsed)
    reservation_repo.assign_to_spot(
        reservation.id, spot_id,
        f"Walk-in erfasst auf Platz {spot_number}"
    )
    db.commit()
    return RedirectResponse(url=f"/karte?spot_id={spot_id}", status_code=303)


@app.post("/karte/auto-place")
async def karte_auto_place(
    request: Request,
    db: Session = Depends(get_db)
):
    """Assign every active reservation without a spot to the first free matching spot."""
    if not require_auth(request):
        return RedirectResponse(url="/login", status_code=303)

    reservation_repo = ReservationRepository(db)
    spot_repo = ParkingSpotRepository(db)

    unassigned = reservation_repo.find_active_without_spot()
    used_spot_ids = set()

    for res in unassigned:
        # WOMEN spots are never auto-assigned.
        # Vehicles without a declared type default to TRUCK, falling back to CAR.
        chosen = None
        for spot_type in ("TRUCK", "CAR"):
            for spot in spot_repo.get_free_spots(spot_type):
                if spot.id not in used_spot_ids:
                    chosen = spot
                    break
            if chosen:
                break

        if chosen:
            used_spot_ids.add(chosen.id)
            reservation_repo.assign_to_spot(
                res.id,
                chosen.id,
                f"automatisch zugewiesen zu Platz {chosen.spot_number}",
            )

    db.commit()
    return RedirectResponse(url="/karte", status_code=303)
@bp.route('/spots/<int:spot_id>/panel')
@login_required
def spot_panel(spot_id):
    """Lädt den Inhalt des Seitenpanels für einen Spot."""
    spot = ParkingSpot.query.get_or_404(spot_id)
    # Hole alle aktiven Reservierungen für die Picker-Liste
    all_reservations = Reservation.query.filter(
        Reservation.status.in_(['NEW', 'CONFIRMED']),
        Reservation.valid_from <= datetime.now(timezone.utc),
        Reservation.valid_until >= datetime.now(timezone.utc)
    ).all()
    
    # Trenne in "Ohne Platz" und "Auf anderem Platz"
    unassigned = [r for r in all_reservations if r.spot_id is None]
    on_other_spots = [r for r in all_reservations if r.spot_id is not None and r.spot_id != spot_id]
    
    return render_template('components/spot_panel_content.html', 
                           spot=spot, 
                           unassigned=unassigned, 
                           on_other_spots=on_other_spots)