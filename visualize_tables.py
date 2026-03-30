# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas", "plotly"]
# ///

import math

import pandas as pd
import plotly.graph_objects as go

INPUT = "data/stats/final_guest_list.csv"
OUTPUT_DIR = "data"

TABLE_RADIUS = 1.0
RECT_W = 1.4  # Monarca rectangle half-width
RECT_H = 0.5  # Monarca rectangle half-height

# Venue layout positions (x, y) matching the actual floor plan.
# Left = Patio 1, Right = Patio 2, Center = Monarca (Novios).
SP = 3.2  # spacing unit

TABLE_POSITIONS = {
    # --- Patio 1 (left) ---
    # Top row
    "Morfo Azul":        (0 * SP,       1 * SP),
    "Tigre":             (1 * SP,       1 * SP),
    "Nacarada":          (2 * SP,       1 * SP),
    # Bottom row
    "Cola de Golondrina": (0 * SP,       0 * SP),
    "Alas de Cristal":    (1 * SP,       0 * SP),
    "Aurora":             (2 * SP,       0 * SP),
    # --- Monarca (center, bottom of dance floor) ---
    "Monarca":           (3.6 * SP,    -1.2 * SP),
    # --- Patio 2 (right) ---
    # Top row
    "Zafiro":            (5.5 * SP,     1.6 * SP),
    "Esmeralda":         (6.9 * SP,     1.6 * SP),
    # Middle row
    "Virrey":            (5.1 * SP,     0.0 * SP),
    "Malaquita":         (6.2 * SP,     0.0 * SP),
    "Almirante Rojo":    (7.3 * SP,     0.0 * SP),
    # Bottom row
    "Azul de Adonis":    (5.5 * SP,    -1.5 * SP),
    "Cebra":             (6.9 * SP,    -1.5 * SP),
}

# Color palettes per view
VIEW_COLORS = {
"entry": {
        "colors": {
            "Burrata con prosciutto": "#7B68EE",
            "Terrina de dos salmones": "#F4845F",
            "Kids Food": "#77DD77",
        },
        "title": "Table Assignments — Entries",
    },
    "main_course": {
        "colors": {
            "Filete de res con risotto de hongos": "#7B68EE",
            "Salmón con risotto de verduras": "#F4845F",
            "Kids Food": "#77DD77",
        },
        "title": "Table Assignments — Main Courses",
    },
}


def make_hover(row):
    lines = [f"<b>{row['member']}</b>"]
    if row["is_plus_one"] and str(row["is_plus_one"]).strip():
        lines.append(f"Plus one of: {row['is_plus_one']}")
    lines.append(f"Entry: {row['entry']}")
    lines.append(f"Main: {row['main_course']}")
    if str(row.get("is_under_18", "")).lower() == "true":
        lines.append("Under 18")
    if row.get("allergies") and str(row["allergies"]).strip() and str(row["allergies"]) != "nan":
        lines.append(f"Allergies: {row['allergies']}")
    if row.get("notes") and str(row["notes"]).strip() and str(row["notes"]) != "nan":
        lines.append(f"Notes: {row['notes']}")
    return "<br>".join(lines)


def get_color(guest, view):
    if view == "entry":
        return VIEW_COLORS[view]["colors"].get(guest["entry"], "#CCCCCC")
    elif view == "main_course":
        return VIEW_COLORS[view]["colors"].get(guest["main_course"], "#CCCCCC")


def rect_perimeter_point(cx, cy, hw, hh, t):
    """Return (x, y, outward_angle) for parameter t in [0, 1) along a rectangle centred at (cx, cy)."""
    perim = 4 * (2 * hw + 2 * hh)  # not needed — we work in normalised t
    # Walk the perimeter: top → right → bottom → left
    sides = [
        (2 * hw, lambda f: (cx - hw + f * 2 * hw, cy + hh,  math.pi / 2)),   # top edge (left→right)
        (2 * hh, lambda f: (cx + hw,              cy + hh - f * 2 * hh, 0)),  # right edge (top→bottom)
        (2 * hw, lambda f: (cx + hw - f * 2 * hw, cy - hh, -math.pi / 2)),   # bottom edge (right→left)
        (2 * hh, lambda f: (cx - hw,              cy - hh + f * 2 * hh, math.pi)),  # left edge (bottom→top)
    ]
    total = sum(s[0] for s in sides)
    d = (t % 1.0) * total
    for length, fn in sides:
        if d <= length:
            x, y, angle = fn(d / length if length else 0)
            return x, y, angle
        d -= length
    return sides[-1][1](1.0)  # fallback


def build_figure(df, view):
    tables = sorted(df["table_name"].unique())

    fig = go.Figure()

    # Dance floor rectangle between the two patios
    df_x0, df_x1 = 2.7 * SP, 4.5 * SP
    df_y0, df_y1 = -0.8 * SP, 1.4 * SP
    fig.add_shape(
        type="rect", x0=df_x0, y0=df_y0, x1=df_x1, y1=df_y1,
        fillcolor="rgba(220, 210, 240, 0.25)",
        line=dict(color="rgba(180,170,200,0.5)", width=1.5, dash="dot"),
    )
    fig.add_annotation(
        x=(df_x0 + df_x1) / 2, y=df_y1 - 0.3,
        text="<b>Pista</b>",
        showarrow=False,
        font=dict(size=13, color="#999"),
    )
    # DJ at the top of the dance floor
    fig.add_annotation(
        x=(df_x0 + df_x1) / 2, y=df_y1 + 0.3,
        text="DJ",
        showarrow=False,
        font=dict(size=11, color="#bbb"),
    )

    for table_name in tables:
        cx, cy = TABLE_POSITIONS[table_name]

        guests = df[df["table_name"] == table_name]
        if "seat_order" in guests.columns:
            guests = guests.sort_values("seat_order")
        guests = guests.reset_index(drop=True)
        n = len(guests)

        is_rect = table_name == "Monarca"

        xs, ys, hovers, colors = [], [], [], []
        label_positions = []
        for i, (_, guest) in enumerate(guests.iterrows()):
            if is_rect:
                # Seat guests evenly along the bottom edge (left to right)
                frac = (i + 1) / (n + 1)  # even spacing within edge
                x = cx - RECT_W + frac * 2 * RECT_W
                y = cy - RECT_H
                angle = -math.pi / 2  # outward = downward
                xs.append(x)
                ys.append(y)
                label_positions.append((
                    x + 0.35 * math.cos(angle),
                    y + 0.35 * math.sin(angle),
                ))
            else:
                angle = math.pi / 2 - 2 * math.pi * i / n
                xs.append(cx + TABLE_RADIUS * math.cos(angle))
                ys.append(cy + TABLE_RADIUS * math.sin(angle))
                label_positions.append((
                    cx + (TABLE_RADIUS + 0.35) * math.cos(angle),
                    cy + (TABLE_RADIUS + 0.35) * math.sin(angle),
                ))
            hovers.append(make_hover(guest))
            colors.append(get_color(guest, view))

        # Table outline
        if is_rect:
            pad = 0.25
            fig.add_shape(
                type="rect",
                x0=cx - RECT_W - pad, y0=cy - RECT_H - pad,
                x1=cx + RECT_W + pad, y1=cy + RECT_H + pad,
                fillcolor="rgba(0,0,0,0)",
                line=dict(color="rgba(180,180,180,0.4)", width=1.5),
            )
        else:
            circle_x = [cx + TABLE_RADIUS * 1.25 * math.cos(a) for a in [i * 2 * math.pi / 60 for i in range(61)]]
            circle_y = [cy + TABLE_RADIUS * 1.25 * math.sin(a) for a in [i * 2 * math.pi / 60 for i in range(61)]]
            fig.add_trace(go.Scatter(
                x=circle_x, y=circle_y,
                mode="lines",
                line=dict(color="rgba(180,180,180,0.4)", width=1.5),
                hoverinfo="skip",
                showlegend=False,
            ))

        # Table label
        fig.add_annotation(
            x=cx, y=cy,
            text=f"<b>{table_name}</b><br><sub>{n} guests</sub>",
            showarrow=False,
            font=dict(size=11, color="#444"),
        )

        # Guest markers
        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode="markers",
            marker=dict(size=18, color=colors, line=dict(width=1.5, color="white")),
            text=hovers,
            hoverinfo="text",
            showlegend=False,
        ))

        # Guest name labels
        for i, (_, guest) in enumerate(guests.iterrows()):
            lx, ly = label_positions[i]
            first_name = guest["member"].split()[0]
            fig.add_annotation(
                x=lx, y=ly,
                text=first_name,
                showarrow=False,
                font=dict(size=8, color="#666"),
            )

    # Legend
    color_map = VIEW_COLORS[view]["colors"]
    for label, color in color_map.items():
        display_label = label.replace("_", " ").title()
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(size=12, color=color),
            name=display_label,
        ))

    fig.update_layout(
        title=dict(text=VIEW_COLORS[view]["title"], font=dict(size=22)),
        width=1900,
        height=1000,
        xaxis=dict(visible=False, scaleanchor="y"),
        yaxis=dict(visible=False),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=40, r=40, t=80, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
    )

    return fig


NAV_BAR = """
<div style="font-family: Georgia, serif; text-align: center; padding: 12px 0; border-bottom: 1px solid #e8e3dd; background: #faf9f6;">
  <a href="../index.html" style="color: #b08d6e; text-decoration: none; margin: 0 18px; font-size: 0.95rem; letter-spacing: 0.04em;">Home</a>
  <a href="tables_entry.html" style="color: #b08d6e; text-decoration: none; margin: 0 18px; font-size: 0.95rem; letter-spacing: 0.04em;" {active_entry}>Entries</a>
  <a href="tables_main_course.html" style="color: #b08d6e; text-decoration: none; margin: 0 18px; font-size: 0.95rem; letter-spacing: 0.04em;" {active_main_course}>Main Courses</a>
</div>
"""


def main():
    df = pd.read_csv(INPUT)
    df = df.fillna("")

    for view in VIEW_COLORS:
        fig = build_figure(df, view)
        output = f"{OUTPUT_DIR}/tables_{view}.html"
        html = fig.to_html(full_html=True)
        # Build nav with active styling
        active = {f"active_{v}": "" for v in VIEW_COLORS}
        active[f"active_{view}"] = 'style="color: #2c2c2c; font-weight: bold; border-bottom: 2px solid #b08d6e; padding-bottom: 4px;"'
        nav = NAV_BAR.format(**active)
        html = html.replace("<body>", f"<body>{nav}", 1)
        with open(output, "w") as f:
            f.write(html)
        print(f"Saved {output}")


if __name__ == "__main__":
    main()
