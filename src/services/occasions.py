from datetime import date, datetime

import holidays


def future_egypt_occasions(today: date | None = None) -> list[str]:
    current_date = today or datetime.now().date()
    egypt_holidays = holidays.Egypt(
        years=[current_date.year, current_date.year + 1]
    )

    return [
        f"{occasion_date.strftime('%A, %B %d, %Y')}: {name}"
        for occasion_date, name in sorted(egypt_holidays.items())
        if occasion_date >= current_date
    ]
