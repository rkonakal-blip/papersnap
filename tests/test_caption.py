"""Tests for caption regex patterns and body-reference guard."""

import pytest
from papersnap.caption import _CAPTION_STRICT, _CAPTION_SPATIAL, _BODY_REF


# ---------------------------------------------------------------------------
# Strict pattern — separator required
# ---------------------------------------------------------------------------

STRICT_MATCHES = [
    "Fig. 1. Block diagram of the control strategy.",
    "Figure 1: Overview of the proposed method.",
    "Fig. 2— Experimental setup.",
    "FIGURE 3. Results summary.",
    "Fig. S1. Supplementary data.",
    "Fig. 1A. Panel description.",
    "Figure 10: Multi-panel overview.",
    "Fig. 1 | Nature-style caption.",
    "Fig. 1, Caption with comma separator.",
]

STRICT_NON_MATCHES = [
    "Fig. 1 shows the block diagram",       # body reference — no separator
    "Figure 2 demonstrates the results",    # body reference — no separator
    "As shown in Fig. 3, the results",      # mid-sentence reference
    "See Figure 4 for details.",            # inline reference
    "fig1.png",                             # filename
    "This is a normal sentence.",
]

@pytest.mark.parametrize("text", STRICT_MATCHES)
def test_strict_matches(text):
    assert _CAPTION_STRICT.match(text), f"Expected strict match: {text!r}"

@pytest.mark.parametrize("text", STRICT_NON_MATCHES)
def test_strict_non_matches(text):
    assert not _CAPTION_STRICT.match(text), f"Expected no strict match: {text!r}"


# ---------------------------------------------------------------------------
# Spatial pattern — no separator required
# ---------------------------------------------------------------------------

SPATIAL_MATCHES = [
    "Fig. 1 Block diagram of the control strategy.",   # Nature style
    "Figure 1 Overview of the proposed method.",
    "Fig. 1. With separator also matches.",
    "Fig. S2A Supplementary panel.",
    "FIGURE 3 Results summary.",
]

SPATIAL_NON_MATCHES = [
    "As shown in Fig. 3, the results",
    "See Figure 4 for details.",
    "This is a normal sentence.",
]

@pytest.mark.parametrize("text", SPATIAL_MATCHES)
def test_spatial_matches(text):
    assert _CAPTION_SPATIAL.match(text), f"Expected spatial match: {text!r}"

@pytest.mark.parametrize("text", SPATIAL_NON_MATCHES)
def test_spatial_non_matches(text):
    assert not _CAPTION_SPATIAL.match(text), f"Expected no spatial match: {text!r}"


# ---------------------------------------------------------------------------
# Body-reference guard
# ---------------------------------------------------------------------------

BODY_REFS = [
    "Fig. 1 shows the proposed architecture.",
    "Figure 2 demonstrates the improvement.",
    "Fig. 3 illustrates the pipeline.",
    "Figure 4 depicts the experimental setup.",
    "Fig. 5 indicates a clear trend.",
    "Figure 6 presents the comparison.",
    "Fig. 7 reveals an interesting pattern.",
    "Figure 8 displays the output.",
    "Fig. 9 compares the two methods.",
    "Figure 10 summarizes the findings.",
    "Fig. 1 confirms the hypothesis.",
    "Figure 2 provides an overview.",
]

NOT_BODY_REFS = [
    "Fig. 1. Block diagram of the system.",     # actual caption
    "Figure 1: Overview of the method.",        # actual caption
    "Fig. 1 | Nature caption.",                 # actual caption
    "Fig. S1A. Supplementary figure.",          # actual caption
]

@pytest.mark.parametrize("text", BODY_REFS)
def test_body_ref_matches(text):
    assert _BODY_REF.match(text), f"Expected body-ref match: {text!r}"

@pytest.mark.parametrize("text", NOT_BODY_REFS)
def test_body_ref_non_matches(text):
    assert not _BODY_REF.match(text), f"Expected no body-ref match: {text!r}"


# ---------------------------------------------------------------------------
# Interaction: spatial matches body refs (they should both fire)
# ---------------------------------------------------------------------------

def test_body_ref_is_also_spatial():
    """Body references match the spatial pattern — the guard must be applied explicitly."""
    text = "Fig. 1 shows the proposed architecture."
    assert _CAPTION_SPATIAL.match(text)
    assert _BODY_REF.match(text)


def test_real_caption_is_spatial_not_body_ref():
    text = "Fig. 1 Overview of the proposed method."
    assert _CAPTION_SPATIAL.match(text)
    assert not _BODY_REF.match(text)
