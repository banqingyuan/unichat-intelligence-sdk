def seconds_to_english_readable(seconds):
    # Define time units in seconds
    MINUTE = 60
    HOUR = 60 * MINUTE
    DAY = 24 * HOUR
    MONTH = 30 * DAY
    YEAR = 365 * DAY

    if seconds < DAY:
        return "today"
    if seconds < 7 * DAY:
        return "a few days"
    if seconds < 30 * DAY:
        return "a few weeks"
    if seconds < 365 * DAY:
        return "a few months"

    # # Calculate time components
    # years, seconds = divmod(seconds, YEAR)
    # months, seconds = divmod(seconds, MONTH)
    # days, seconds = divmod(seconds, DAY)
    # hours, seconds = divmod(seconds, HOUR)
    # minutes, seconds = divmod(seconds, MINUTE)
    #
    # # Create the human-readable string
    # parts = []
    # if years:
    #     parts.append(f"{years} year{'s' if years != 1 else ''}")
    # if months and len(parts) < 2:
    #     parts.append(f"{months} month{'s' if months != 1 else ''}")
    # if days and len(parts) < 2:
    #     parts.append(f"{days} day{'s' if days != 1 else ''}")
    # if hours and len(parts) < 2:
    #     parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    # if minutes and len(parts) < 2:
    #     parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    # if not parts or (len(parts) < 2 and seconds):
    #     parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
    #
    # # Join the parts into a single string
    # if len(parts) == 1:
    #     return f"{parts[0]} ago"
    # else:
    #     time_str = " and ".join(parts)
    #     return f"{time_str} ago"


if __name__ == '__main__':
    print(seconds_to_english_readable(98765432))