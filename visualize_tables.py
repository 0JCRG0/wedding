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
    # --- Monarca (center, between patios) ---
    "Monarca":           (1 * SP,      -1.3 * SP),
    # --- Patio 2 (right) ---
    # Top row
    "Zafiro":            (3.8 * SP,     1.5 * SP),
    "Esmeralda":         (5.0 * SP,     1.5 * SP),
    # Middle row
    "Virrey":            (3.5 * SP,     0.3 * SP),
    "Malaquita":         (4.4 * SP,     0.3 * SP),
    "Almirante Rojo":    (5.3 * SP,     0.3 * SP),
    # Bottom row
    "Azul de Adonis":    (3.8 * SP,    -0.9 * SP),
    "Cebra":             (5.0 * SP,    -0.9 * SP),
}

# Color palettes per view
VIEW_COLORS = {
    "guest_type": {
        "colors": {"primary": "#7B68EE", "plus_one": "#F4845F"},
        "title": "Table Assignments — Guest Type",
    },
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
    if view == "guest_type":
        is_plus_one = str(guest["is_plus_one"]).strip() != ""
        return VIEW_COLORS[view]["colors"]["plus_one" if is_plus_one else "primary"]
    elif view == "entry":
        return VIEW_COLORS[view]["colors"].get(guest["entry"], "#CCCCCC")
    elif view == "main_course":
        return VIEW_COLORS[view]["colors"].get(guest["main_course"], "#CCCCCC")


def build_figure(df, view):
    tables = sorted(df["table_name"].unique())

    fig = go.Figure()

    for table_name in tables:
        cx, cy = TABLE_POSITIONS[table_name]

        guests = df[df["table_name"] == table_name]
        if "seat_order" in guests.columns:
            guests = guests.sort_values("seat_order")
        guests = guests.reset_index(drop=True)
        n = len(guests)

        xs, ys, hovers, colors = [], [], [], []
        for i, (_, guest) in enumerate(guests.iterrows()):
            angle = 2 * math.pi * i / n - math.pi / 2
            xs.append(cx + TABLE_RADIUS * math.cos(angle))
            ys.append(cy + TABLE_RADIUS * math.sin(angle))
            hovers.append(make_hover(guest))
            colors.append(get_color(guest, view))

        # Table circle outline
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
            angle = 2 * math.pi * i / n - math.pi / 2
            lx = cx + (TABLE_RADIUS + 0.35) * math.cos(angle)
            ly = cy + (TABLE_RADIUS + 0.35) * math.sin(angle)
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
        width=1600,
        height=1000,
        xaxis=dict(visible=False, scaleanchor="y"),
        yaxis=dict(visible=False),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=40, r=40, t=80, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
    )

    return fig


def main():
    df = pd.read_csv(INPUT)
    df = df.fillna("")

    for view in VIEW_COLORS:
        fig = build_figure(df, view)
        output = f"{OUTPUT_DIR}/tables_{view}.html"
        fig.write_html(output)
        print(f"Saved {output}")


if __name__ == "__main__":
    main()
