from __future__ import annotations


class CenterCrop:
    """Cover target box then center crop; yuv420p for mobile/VT play safety."""

    name = "center_crop"

    def video_filter(self, *, src_w: int, src_h: int, out_w: int, out_h: int) -> str:
        # src_w/src_h kept for logging / future strategies; cover formula is scale-based.
        _ = (src_w, src_h)
        return (
            f"scale=w={out_w}:h={out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h},"
            f"format=yuv420p"
        )
