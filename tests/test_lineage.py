from snpit.lineage import Lineage
import csv
from pathlib import Path


def test_equalityOperator_twoEqualReturnsTrue():
    lineage1 = Lineage(name="test", lineage="Lineage 5")
    lineage2 = Lineage(name="test", lineage="Lineage 6")

    assert lineage1 == lineage2


def test_equalityOperator_twoNonEqualReturnsFalse():
    lineage1 = Lineage(name="foo", lineage="Lineage 5")
    lineage2 = Lineage(name="test", lineage="Lineage 6")

    assert not (lineage1 == lineage2)


def test_inequalityOperator_twoEqualReturnsFalse():
    lineage1 = Lineage(name="test", lineage="Lineage 5")
    lineage2 = Lineage(name="test", lineage="Lineage 6")

    assert not (lineage1 != lineage2)


def test_inequalityOperator_twoNonEqualReturnsTrue():
    lineage1 = Lineage(name="foo", lineage="Lineage 5")
    lineage2 = Lineage(name="test", lineage="Lineage 6")

    assert lineage1 != lineage2


def test_addSnps_emptyFileSnpsRemainEmpty():
    lineage_variant_file = Path("test_cases/empty.tsv")
    lineage = Lineage()
    lineage.add_snps(lineage_variant_file)

    actual = lineage.snps
    expected = dict()

    assert actual == expected


def test_addSnps_realFileSnpsContainAllEntries():
    lineage_variant_file = Path("test_cases/test_lineage.tsv")
    lineage = Lineage()
    lineage.add_snps(lineage_variant_file)

    actual = lineage.snps
    expected = {
        1_011_511: "C",
        1_022_003: "C",
        1_028_217: "A",
        1_034_758: "T",
        1_071_966: "G",
    }

    assert actual == expected


def test_fromCsvEntry_emptyEntryReturnsEmptyLineage():
    entry = dict()

    actual = Lineage.from_csv_entry(entry)
    expected = Lineage()

    assert actual == expected


def test_fromCsvEntry_realEntryEntryReturnsLineage():
    library = csv.DictReader(Path("test_cases/test_library.csv").open())
    entry = next(library)

    actual = Lineage.from_csv_entry(entry)
    expected = Lineage(
        species="M. tuberculosis",
        lineage="Lineage 1",
        sublineage="Sublineage 7",
        name="indo-oceanic",
    )

    assert actual == expected
