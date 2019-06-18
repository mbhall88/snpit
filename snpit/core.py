#! /usr/bin/env python
import sys
import csv
import gzip
import operator
from pathlib import Path
from typing import List

import vcf
from Bio import SeqIO

from .genotype import Genotype
from .lineage import Lineage

LIBRARY_DIR = Path("lib").absolute()


class snpit(object):
    """
    The snpit class is designed to take a VCF file and return the most likely lineage
    based on Sam Lipworth's SNP-IT.

    The methods have been separated so it can be incorporated into single Python
    scripts that processes multiple VCF files.
    """

    def __init__(self, input_file: str, threshold: float, ignore_filter=False):

        """
        Args:
            input_file: FASTA/VCF file to read variants from.
            threshold: The percentage of snps above which a sample is
            considered to belong to a lineage.
            ignore_filter: Whether to ignore the FILTER column in VCF input.
        """
        self.threshold = threshold
        self.ignore_filter = ignore_filter

        # library file which contains a list of all the lineages and sub-lineages
        library_csv = LIBRARY_DIR / "library.csv"

        self.lineages = load_lineages_from_csv(library_csv)
        self.add_snps_to_all_lineages()

        compressed = True if input_file.endswith("gz") else False
        suffixes = Path(input_file).suffixes

        if ".vcf" in suffixes:
            self.classify_vcf(input_file)
        elif any(ext in suffixes for ext in [".fa", ".fasta"]):
            self.load_fasta(input_file, compression=compressed)
        else:
            raise Exception(
                "Only VCF and FASTA files are allowed as inputs (may be compressed with gzip,bzip2)"
            )

        # then work out the lineage
        (
            self.species,
            self.lineage,
            self.sublineage,
            self.percentage,
        ) = self.determine_lineage()

    def add_snps_to_all_lineages(self):
        for lineage in self.lineages:
            lineage_variants_file = LIBRARY_DIR / lineage.name

            if not lineage_variants_file.exists():
                print(
                    "Lineage file {} does not exist for lineage {}".format(
                        lineage_variants_file, lineage.name
                    ),
                    file=sys.stderr,
                )
                continue

            lineage.add_snps(lineage_variants_file)

    def classify_vcf(self, vcf_file):
        """Loads the vcf file and then, for each lineage, identify the base at each of
        the identifying positions in the genome.

        Args:
            vcf_file (str): Path to the VCF file to be read
        """

        # setup the dictionaries of expected SNPs for each lineage
        self._reset_lineage_snps()

        # open the VCF file for reading
        vcf_reader = vcf.Reader(open(vcf_file, "r"))

        # read the VCF file line-by-line
        for record in vcf_reader:
            if self.ignore_filter or record.FILTER:
                self.lineage_classify_position(record)

    def lineage_classify_position(self, record):
        """Determine what lineage(s) (if any) a VCF record belongs to.

        Args:
            record (vcf.model._Record): A VCF record object.
        """
        for lineage_name in self.lineages:
            lineage_positions = self.reference_snps[lineage_name].keys()

            if record.POS not in lineage_positions:
                continue

            for sample in record.samples:
                genotype = Genotype.from_string(sample["GT"])
                variant = self.get_sample_genotyped_variant(genotype, record)

                if variant is not None:
                    self.sample_snps[lineage_name][record.POS] = variant

    @staticmethod
    def get_sample_genotyped_variant(genotype, record):
        """Retrieves the variant to replace the reference base with for a sample based
        on it's genotype call.

        Args:
            genotype (Genotype): The genotype call for the sample.
            record (vcf.model._Record): A VCF record object.
        Returns:
            str or None: A hyphen if the call is null (ie ./.) or the alt variant if
            the call is alt. Returns None is the call is ref or heterozygous.
        """
        if genotype.is_reference() or genotype.is_heterozygous():
            return None
        elif genotype.is_null():
            # record a hyphen which won't match, regardless of the reference
            return "-"
        elif genotype.is_alt():
            # replace the H37Rv base with the actual base from the VCF file
            alt_variant = record.ALT[int(genotype.call()[0]) - 1]
            return alt_variant

    def load_fasta(self, fasta_file, compression=False):
        """
        Loads a supplied fasta file and then, for each lineage, identify the base at
        each of the identifying positions

        Args:
         fasta_file (str): Path to the fasta file to be read
         compression (bool): whether the fasta file is compressed by gz or bzip2
        """

        # setup the dictionaries of expected SNPs for each lineage
        self._reset_lineage_snps()
        self.sample_snps = {}

        # open the fasta file for reading
        open_fn = gzip.open if compression else open

        with open_fn(fasta_file, "rt") as fasta_file:
            fasta_reader = SeqIO.read(fasta_file, "fasta")

        #  iterate through the lineages
        for lineage_name in self.lineages:

            self.sample_snps[lineage_name] = {}

            # iterate over the positions in the reference set of snps for that lineage
            for pos in self.reference_snps[lineage_name]:
                if pos in self.reference_snps[lineage_name].keys():

                    # CAUTION the GenBank File is 1-based, but the lineage files are 0-based
                    # Remember the nucleotide at the defining position
                    self.sample_snps[lineage_name][int(pos)] = fasta_reader.seq[
                        int(pos) - 1
                    ]

    def _reset_lineage_snps(self):
        """
        For each lineage creates a dictionary of the positions and expected nucleotides
        for TB that define that lineage.

        This is required because the VCF files only list changes relative to H37Rv.
        Hence these dictionaries are then changed when mutations at these positions are
        encountered.
        """

        # make the relative path to the H37Rv TB reference GenBank file
        genbank_path = LIBRARY_DIR / "H37Rv.gbk"

        # read the reference genome using BioPython
        with genbank_path.open() as genbank_file:
            reference_genome = SeqIO.read(genbank_file, "genbank")

        self.sample_snps = {}

        #  iterate through the lineages
        for lineage_name in self.lineages:

            self.sample_snps[lineage_name] = {}

            # iterate over the positions in the reference set of snps for that lineage
            for pos in self.reference_snps[lineage_name]:

                # CAUTION the GenBank File is 1-based, but the lineage files are 0-based
                # Remember the nucleotide at the defining position
                self.sample_snps[lineage_name][int(pos)] = reference_genome.seq[
                    int(pos) - 1
                ]

    def determine_lineage(self):
        """
        Having read the VCF file, for each lineage, calculate the percentage of SNP
        present in the sample.
        Note that this means the percentages will not add up to 100%.

        Returns:
            tuple of (lineage,percentage)
        """

        self.percentage = {}

        # consider lineage-by-lineage
        for lineage_name in self.lineages:

            reference_set = []

            shared = 0
            ref = 0

            for i, j in enumerate(self.reference_snps[lineage_name]):

                if (
                    self.reference_snps[lineage_name][j]
                    == self.sample_snps[lineage_name][j]
                ):
                    shared += 1
                ref += 1

            # thereby calculate the percentage of SNPs in this sample that match the lineage
            self.percentage[lineage_name] = (shared / ref) * 100

        # create an ordered list of tuples of (lineage,percentage) in descending order
        self.results = sorted(
            self.percentage.items(), key=operator.itemgetter(1), reverse=True
        )

        identified_lineage_name = self.results[0][0]
        identified_lineage_percentage = self.results[0][1]

        # if the top lineage is above the specified threshold, return the classification
        if identified_lineage_percentage > self.threshold:

            # look at the next-highest lineage if the top one is Lineage 4 but with no sublineage
            if (
                self.lineages[identified_lineage_name]["lineage"] == "Lineage 4"
                and self.lineages[identified_lineage_name]["sublineage"] == ""
            ):

                next_lineage_name = self.results[1][0]
                next_lineage_percentage = self.results[1][1]

                # if the next best lineage is ALSO lineage 4, but this one has a
                # sublineage and is above the threshold, report that one instead
                if (
                    self.lineages[next_lineage_name]["lineage"] == "Lineage 4"
                    and self.lineages[next_lineage_name]["sublineage"] != ""
                    and next_lineage_percentage > self.threshold
                ):

                    identified_lineage_name = next_lineage_name

            return (
                self.lineages[identified_lineage_name]["species"],
                self.lineages[identified_lineage_name]["lineage"],
                self.lineages[identified_lineage_name]["sublineage"],
                identified_lineage_percentage,
            )

        # finally, no strain must be above the threshold percentage so return Nones as "Don't know"
        else:
            return (None, None, None, None)


def load_lineages_from_csv(filepath: Path) -> List[Lineage]:
    """Load lineage metadata from a CVS file and return as a list of Lineages."""
    library = csv.DictReader(filepath.open())
    lineages = []

    for entry in library:
        lineages.append(Lineage.from_csv_entry(entry))

    return lineages
