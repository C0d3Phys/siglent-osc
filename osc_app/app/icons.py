"""Íconos planos generados por código para la barra de herramientas.

Se dibujan con ``QPainter`` en vez de usar los íconos nativos del sistema
operativo (``QStyle.StandardPixmap``), que varían de estilo entre
plataformas y suelen verse anticuados o inconsistentes con el resto de la
interfaz. Todos comparten el mismo grosor de trazo y color, sin relleno,
para lograr un aspecto uniforme.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

_SIZE = 28
_MARGIN_RATIO = 0.18
_STROKE_WIDTH = 2.1


def _new_canvas(size: int) -> tuple[QPixmap, QPainter]:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    return pixmap, painter


def _make_pen(color: QColor) -> QPen:
    pen = QPen(color)
    pen.setWidthF(_STROKE_WIDTH)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _draw_open(painter: QPainter, rect: QRectF) -> None:
    """Carpeta simplificada: pestaña + cuerpo."""
    tab_height = rect.height() * 0.18
    tab_rect = QRectF(rect.left(), rect.top(), rect.width() * 0.5, tab_height * 1.3)
    body_rect = QRectF(
        rect.left(), rect.top() + tab_height, rect.width(), rect.height() - tab_height
    )
    painter.drawRoundedRect(tab_rect, 2, 2)
    painter.drawRoundedRect(body_rect, 3, 3)


def _draw_save_image(painter: QPainter, rect: QRectF) -> None:
    """Ícono de imagen: marco, sol y montaña."""
    painter.drawRoundedRect(rect, 3, 3)
    sun_radius = rect.width() * 0.11
    sun_center = QPointF(rect.left() + rect.width() * 0.28, rect.top() + rect.height() * 0.32)
    painter.drawEllipse(sun_center, sun_radius, sun_radius)
    path = QPainterPath()
    path.moveTo(rect.left() + rect.width() * 0.06, rect.bottom() - rect.height() * 0.12)
    path.lineTo(rect.left() + rect.width() * 0.38, rect.top() + rect.height() * 0.55)
    path.lineTo(rect.left() + rect.width() * 0.58, rect.top() + rect.height() * 0.76)
    path.lineTo(rect.left() + rect.width() * 0.80, rect.top() + rect.height() * 0.48)
    path.lineTo(rect.right() - rect.width() * 0.05, rect.bottom() - rect.height() * 0.12)
    painter.drawPath(path)


def _draw_cursor_x(painter: QPainter, rect: QRectF) -> None:
    """Dos cursores verticales con marcas en los extremos."""
    top = rect.top() + rect.height() * 0.10
    bottom = rect.bottom() - rect.height() * 0.10
    tick = rect.width() * 0.14
    for x in (rect.left() + rect.width() * 0.32, rect.left() + rect.width() * 0.68):
        painter.drawLine(QPointF(x, top), QPointF(x, bottom))
        painter.drawLine(QPointF(x - tick / 2, top), QPointF(x + tick / 2, top))
        painter.drawLine(QPointF(x - tick / 2, bottom), QPointF(x + tick / 2, bottom))


def _draw_cursor_y(painter: QPainter, rect: QRectF) -> None:
    """Dos cursores horizontales con marcas en los extremos."""
    left = rect.left() + rect.width() * 0.10
    right = rect.right() - rect.width() * 0.10
    tick = rect.height() * 0.14
    for y in (rect.top() + rect.height() * 0.32, rect.top() + rect.height() * 0.68):
        painter.drawLine(QPointF(left, y), QPointF(right, y))
        painter.drawLine(QPointF(left, y - tick / 2), QPointF(left, y + tick / 2))
        painter.drawLine(QPointF(right, y - tick / 2), QPointF(right, y + tick / 2))


def _draw_auto_y(painter: QPainter, rect: QRectF) -> None:
    """Flecha vertical doble (escala automática)."""
    cx = rect.center().x()
    top = rect.top() + rect.height() * 0.08
    bottom = rect.bottom() - rect.height() * 0.08
    arrow = rect.width() * 0.20
    painter.drawLine(QPointF(cx, top), QPointF(cx, bottom))
    painter.drawLine(QPointF(cx, top), QPointF(cx - arrow, top + arrow))
    painter.drawLine(QPointF(cx, top), QPointF(cx + arrow, top + arrow))
    painter.drawLine(QPointF(cx, bottom), QPointF(cx - arrow, bottom - arrow))
    painter.drawLine(QPointF(cx, bottom), QPointF(cx + arrow, bottom - arrow))


def _draw_region(painter: QPainter, rect: QRectF) -> None:
    """Corchetes de esquina que delimitan una región (zoom a selección)."""
    inset = rect.adjusted(
        rect.width() * 0.06, rect.height() * 0.06, -rect.width() * 0.06, -rect.height() * 0.06
    )
    arm = inset.width() * 0.34
    for corner_point, dx, dy in (
        (inset.topLeft(), arm, 0),
        (inset.topLeft(), 0, arm),
        (inset.topRight(), -arm, 0),
        (inset.topRight(), 0, arm),
        (inset.bottomLeft(), arm, 0),
        (inset.bottomLeft(), 0, -arm),
        (inset.bottomRight(), -arm, 0),
        (inset.bottomRight(), 0, -arm),
    ):
        painter.drawLine(
            corner_point, QPointF(corner_point.x() + dx, corner_point.y() + dy)
        )


def _draw_full_view(painter: QPainter, rect: QRectF) -> None:
    """Marco completo con una línea horizontal (vista de toda la señal)."""
    painter.drawRoundedRect(rect, 3, 3)
    mid_y = rect.center().y()
    painter.drawLine(
        QPointF(rect.left() + rect.width() * 0.16, mid_y),
        QPointF(rect.right() - rect.width() * 0.16, mid_y),
    )


def _draw_math_channel(painter: QPainter, rect: QRectF) -> None:
    """Dos círculos superpuestos (combinar canales)."""
    radius = rect.width() * 0.30
    center = rect.center()
    left_center = QPointF(center.x() - radius * 0.55, center.y())
    right_center = QPointF(center.x() + radius * 0.55, center.y())
    painter.drawEllipse(left_center, radius, radius)
    painter.drawEllipse(right_center, radius, radius)


def _draw_fft(painter: QPainter, rect: QRectF) -> None:
    """Barras de espectro de altura variable."""
    base = rect.bottom() - rect.height() * 0.08
    for x_fraction, height_fraction in (
        (0.10, 0.30),
        (0.31, 0.60),
        (0.52, 0.88),
        (0.73, 0.50),
        (0.92, 0.22),
    ):
        x = rect.left() + rect.width() * x_fraction
        top = base - rect.height() * height_fraction
        painter.drawLine(QPointF(x, base), QPointF(x, top))


_DRAWERS: dict[str, Callable[[QPainter, QRectF], None]] = {
    "open": _draw_open,
    "save_image": _draw_save_image,
    "cursor_x": _draw_cursor_x,
    "cursor_y": _draw_cursor_y,
    "auto_y": _draw_auto_y,
    "region": _draw_region,
    "full_view": _draw_full_view,
    "math_channel": _draw_math_channel,
    "fft": _draw_fft,
}


def make_icon(name: str, color: QColor, size: int = _SIZE) -> QIcon:
    """Genera un ``QIcon`` plano y monocromo para ``name``.

    Lanza ``ValueError`` si ``name`` no corresponde a un ícono conocido, para
    detectar errores de escritura al conectar la barra de herramientas.
    """
    drawer = _DRAWERS.get(name)
    if drawer is None:
        raise ValueError(f"Ícono desconocido: {name!r}. Disponibles: {sorted(_DRAWERS)}")
    pixmap, painter = _new_canvas(size)
    painter.setPen(_make_pen(color))
    margin = size * _MARGIN_RATIO
    rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    drawer(painter, rect)
    painter.end()
    return QIcon(pixmap)
