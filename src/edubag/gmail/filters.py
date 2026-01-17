from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional
import uuid
import xml.etree.ElementTree as ET

from loguru import logger

from edubag.albert.roster import AlbertRoster


def email_query_strings(email_list: list[str], max_length: int = 1500) -> Iterator[str]:
    """
    Concatenates a list of email addresses into query strings,
    joined by " OR ", with each string not exceeding a maximum length.
    This function uses a generator to yield each string one by one.

    Args:
        email_list (list): A list of email address strings.
        max_length (int): The maximum length for each output string.

    Yields:
        str: A string containing a group of "OR"-joined email addresses.
    """
    current_string = ""
    join_str = " OR "

    for email in email_list:
        if len(current_string) + len(join_str) + len(email) > max_length:
            yield current_string
            current_string = email
        else:
            if current_string:
                current_string += join_str + email
            else:
                current_string = email

    if current_string:
        yield current_string


def generate_filter_xml(
    rosters: list[AlbertRoster], label: Optional[str] = None
) -> ET.Element:
    """Generate a Gmail filter XML feed from roster(s)

    Args:
        rosters (list[AlbertRoster]): list of roster objects
        label (string): how they should be labeled. If not set and there's a single roster,
                       create a label from the roster course data. For multiple rosters without
                       a label, each roster gets its own label.
    
    Returns:
        ET.Element: The root <feed> element of the Gmail filter XML
    """
    if not rosters:
        raise ValueError("At least one roster must be provided")

    # Register the 'apps' namespace for correct XML generation
    apps_ns = "http://schemas.google.com/apps/2006"
    ET.register_namespace("apps", apps_ns)

    # Get the current time in ISO 8601 format with 'Z' for UTC
    updated_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Create the root element <feed>
    feed = ET.Element(
        "feed",
        attrib={
            "xmlns": "http://www.w3.org/2005/Atom",
        },
    )

    # Add feed metadata elements
    title = ET.SubElement(feed, "title")
    title.text = "Mail Filters"

    feed_id = ET.SubElement(feed, "id")
    feed_id.text = f"tag:mail.google.com,2008:filters:{uuid.uuid4().hex}"

    updated = ET.SubElement(feed, "updated")
    updated.text = updated_time

    # Generate filter entries for each roster
    for roster in rosters:
        # Determine label for this roster
        if label is None:
            roster_label = roster.course["Class Detail"] + ", " + roster.course["Semester"]
        else:
            roster_label = label

        # Get email addresses from the roster
        addresses = roster.students["Email Address"].tolist()

        # Create entries for this roster's emails
        for filter_value in email_query_strings(addresses):
            entry = ET.SubElement(feed, "entry")

            ET.SubElement(entry, "category", attrib={"term": "filter"})
            entry_title = ET.SubElement(entry, "title")
            entry_title.text = "Mail Filter"
            entry_id = ET.SubElement(entry, "id")
            entry_id.text = f"tag:mail.google.com,2008:filter:{uuid.uuid4().hex}"
            entry_updated = ET.SubElement(entry, "updated")
            entry_updated.text = updated_time
            ET.SubElement(entry, "content")

            ET.SubElement(
                entry,
                f"{{{apps_ns}}}property",
                attrib={"name": "from", "value": filter_value},
            )
            ET.SubElement(
                entry,
                f"{{{apps_ns}}}property",
                attrib={"name": "label", "value": roster_label},
            )
    
    return feed


def filter_from_roster(
    roster: AlbertRoster, label: Optional[str] = None, output: Optional[Path] = None
) -> None:
    """Create a Gmail filter to label senders on a class roster

    Args:
        roster (AlbertRoster): the roster object
        label (string): how they should be labeled. If not set, create a label from the roster course data.
        output (path): where to save the filter. If not set, derive from processed data dir
    """
    filter_from_rosters([roster], label=label, output=output)


def filter_from_rosters(
    rosters: list[AlbertRoster], label: Optional[str] = None, output: Optional[Path] = None
) -> None:
    """Create a Gmail filter to label senders from multiple class rosters

    Creates a single filter file with separate entries for each roster.

    Args:
        rosters (list[AlbertRoster]): list of roster objects
        label (string): how they should be labeled. If not set and there's a single roster,
                       create a label from the roster course data. For multiple rosters without
                       a label, each roster gets its own label.
        output (path): where to save the filter. If not set, save to current directory with
                       a name derived from the roster(s).
    """
    feed = generate_filter_xml(rosters, label=label)

    # Determine output path if not provided
    if output is None:
        if len(rosters) == 1:
            # For single roster, use the original naming scheme
            roster = rosters[0]
            # Try to derive path from the roster if it has a pathstem attribute
            if hasattr(roster, "pathstem"):
                output = Path(f"mailFilters_{roster.pathstem}.xml")
            else:
                # Fallback to a generic name
                output = Path("mailFilters.xml")
        else:
            # For multiple rosters, use a generic combined name
            output = Path("mailFilters_combined.xml")

    # Ensure output directory exists
    output.parent.mkdir(parents=True, exist_ok=True)

    # Create the ElementTree object and write to the file with proper indentation
    tree = ET.ElementTree(feed)
    ET.indent(tree, space="    ", level=0)
    tree.write(output, encoding="UTF-8", xml_declaration=True)

    logger.info(f"XML file '{output}' has been generated successfully.")
