from app.adapters.greenhouse import GreenhouseAdapter


def get_adapter(platform: str, profile: dict | None = None):
    platform = platform.lower().strip()

    if platform == "greenhouse":
        return GreenhouseAdapter(profile=profile)

    raise ValueError(f"Unsupported platform: {platform}")
