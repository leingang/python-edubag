import pandas as pd
from pathlib import Path
from edubag.gradescope.roster import GradescopeRoster
from edubag.brightspace.gradebook import Gradebook


def test_update_sections_from_brightspace_gradebook():
    """Test that sections are correctly extracted from Brightspace gradebook."""
    # Load test data from fixtures
    fixtures_dir = Path(__file__).parent / "fixtures"
    gs_csv = fixtures_dir / "roster.csv"
    bs_csv = fixtures_dir / "gradebook.csv"
    
    # Load the rosters
    gs_roster = GradescopeRoster.from_csv(gs_csv)
    bs_gradebook = Gradebook.from_csv(bs_csv)
    
    # Update sections
    gs_roster.update_sections_from_brightspace_gradebook(bs_gradebook)
    
    # Check that we only have one section column
    assert "Section" in gs_roster.students.columns, "Section column should exist"
    assert "Section 2" not in gs_roster.students.columns, "Section 2 column should not exist"
    
    # Check some specific values
    # Alice is in sections 011, 015 -> should have 015 as the varying section
    alice = gs_roster.students[gs_roster.students["Email"] == "alice.j@university.edu"].iloc[0]
    assert alice["Section"] == "015", f"Alice should be in section 015, got {alice['Section']}"
    
    # Grace is in sections 011, 014 -> should have 014 as the varying section
    grace = gs_roster.students[gs_roster.students["Email"] == "grace.t@university.edu"].iloc[0]
    assert grace["Section"] == "014", f"Grace should be in section 014, got {grace['Section']}"
    
    # Check that NaN values are preserved for students without sections in Brightspace
    # Uma is not in the Brightspace gradebook, so should have NaN section
    uma = gs_roster.students[gs_roster.students["Email"] == "uma.w@university.edu"].iloc[0]
    assert pd.isna(uma["Section"]), f"Uma should have NaN section, got {uma['Section']}"


if __name__ == "__main__":
    test_update_sections_from_brightspace_gradebook()
    print("Test passed!")
