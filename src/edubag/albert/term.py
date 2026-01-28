from enum import Enum


class Season(Enum):
    """Enumeration of academic seasons.
    
    * The values for fall and spring are used to create the term code.
    * The values for the other seasons are guessed.
    """
    JANUARY = 2
    SPRING = 4
    SUMMER = 6
    FALL = 8


class Term(object):
    """An academic term with a year and season."""
    
    year: int
    season: Season

    def __init__(self, year: int, season: Season):
        """Initialize a Term with a year and season.
        
        Args:
            year (int): The academic year.
            season (Season): The season of the term.
        """
        self.year = year
        self.season = season

    @classmethod
    def from_name(cls, name: str) -> "Term":
        """Create a Term object from a term name string like "Fall 2023".
        
        Args:
            name (str): A term name string in the format "{Season} {Year}".
            
        Returns:
            Term: A Term object.
            
        Raises:
            ValueError: If the name format is invalid or season is unknown.
        """
        mapping = {
            "Spring": Season.SPRING,
            "Summer": Season.SUMMER,
            "Fall": Season.FALL,
        }
        parts = name.split()
        if len(parts) != 2:
            raise ValueError(f"Invalid term name format: {name}")
        season_name, year_str = parts
        season = mapping.get(season_name)
        if season is None:
            raise ValueError(f"Unknown season in term name: {season_name}")
        try:
            year = int(year_str)
        except ValueError:
            raise ValueError(f"Invalid year in term name: {year_str}")
        return cls(year=year, season=season)
    
    @property
    def code(self) -> int:
        """Generate a four-digit term code in Albert's scheme.
        
        * The first digit is 1, for an unknown reason.
        * The second and third digits are the last two digits of the year.
        The fourth digit is the number of the academic season.
        """
        return (
            1000
            + (self.year % 100) * 10
            + self.season.value
        )
    
    def __str__(self) -> str:
        """String representation of the Term."""
        return f"{self.season.name} {self.year}"
    
    def __cmp__(self, other: "Term") -> int:
        """
        Compare two Term objects based on their term codes.
        Since the code increases by year and season, this will work correctly.

        Args:
            other (Term): Another Term object to compare with.
        Returns:
            int: Negative if `self < other`, zero if `self == other`, positive if `self > other`.
        """
        return self.code - other.code