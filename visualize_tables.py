# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas", "plotly"]
# ///

import math

import pandas as pd
import plotly.graph_objects as go

INPUT = "data/stats/final_guest_list.csv"
OUTPUT = "data/tables.html"

# Grid layout
COLS = 4
TABLE_SPACING_X = 3.0
TABLE_SPACING_Y = 3.5
TABLE_RADIUS = 1.0


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


def main():
    df = pd.read_csv(INPUT)
    df = df.fillna("")

    tables = sorted(df["table_name"].unique())
    n_tables = len(tables)
    rows_needed = math.ceil(n_tables / COLS)

    fig = go.Figure()

    # Draw each table as a circle of guest markers
    for idx, table_name in enumerate(tables):
        col = idx % COLS
        row = idx // COLS

        cx = col * TABLE_SPACING_X
        cy = (rows_needed - 1 - row) * TABLE_SPACING_Y  # top to bottom

        guests = df[df["table_name"] == table_name]
        if "seat_order" in guests.columns:
            guests = guests.sort_values("seat_order")
        guests = guests.reset_index(drop=True)
        n = len(guests)

        # Place guests in a circle
        xs, ys, hovers, colors = [], [], [], []
        for i, (_, guest) in enumerate(guests.iterrows()):
            angle = 2 * math.pi * i / n - math.pi / 2
            x = cx + TABLE_RADIUS * math.cos(angle)
            y = cy + TABLE_RADIUS * math.sin(angle)
            xs.append(x)
            ys.append(y)
            hovers.append(make_hover(guest))
            is_plus_one = str(guest["is_plus_one"]).strip() != ""
            colors.append("#F4845F" if is_plus_one else "#7B68EE")

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

    # Legend traces
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="markers",
        marker=dict(size=12, color="#7B68EE"),
        name="Primary guest",
    ))
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="markers",
        marker=dict(size=12, color="#F4845F"),
        name="Plus one",
    ))

    fig.update_layout(
        title=dict(text="Wedding Table Assignments", font=dict(size=22)),
        width=COLS * TABLE_SPACING_X * 110 + 100,
        height=rows_needed * TABLE_SPACING_Y * 110 + 100,
        xaxis=dict(visible=False, scaleanchor="y"),
        yaxis=dict(visible=False),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=40, r=40, t=80, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
    )

    fig.write_html(OUTPUT)
    print(f"Saved {OUTPUT}")


if __name__ == "__main__":
    main()
