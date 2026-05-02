"""
Build sample_id -> cancer_label mapping that mirrors TIMER3's 41 categories.

TIMER3 splits BRCA into BRCA, BRCA-Basal, BRCA-Her2, BRCA-LumA, BRCA-LumB
(BRCA itself = all BRCA tumors; the four subtypes are nested subsets).

A single sample therefore maps to MULTIPLE labels, e.g. a BRCA-LumA
tumor sits in both "BRCA" and "BRCA-LumA" rows of the heatmap.
"""
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

# Xena _primary_disease (lower-case strings) -> TCGA short code
DISEASE_TO_CODE = {
    "acute myeloid leukemia": "LAML",
    "adrenocortical cancer": "ACC",
    "bladder urothelial carcinoma": "BLCA",
    "brain lower grade glioma": "LGG",
    "breast invasive carcinoma": "BRCA",
    "cervical & endocervical cancer": "CESC",
    "cholangiocarcinoma": "CHOL",
    "colon adenocarcinoma": "COAD",
    "diffuse large b-cell lymphoma": "DLBC",
    "esophageal carcinoma": "ESCA",
    "glioblastoma multiforme": "GBM",
    "head & neck squamous cell carcinoma": "HNSC",
    "kidney chromophobe": "KICH",
    "kidney clear cell carcinoma": "KIRC",
    "kidney papillary cell carcinoma": "KIRP",
    "liver hepatocellular carcinoma": "LIHC",
    "lung adenocarcinoma": "LUAD",
    "lung squamous cell carcinoma": "LUSC",
    "mesothelioma": "MESO",
    "ovarian serous cystadenocarcinoma": "OV",
    "pancreatic adenocarcinoma": "PAAD",
    "pheochromocytoma & paraganglioma": "PCPG",
    "prostate adenocarcinoma": "PRAD",
    "rectum adenocarcinoma": "READ",
    "sarcoma": "SARC",
    "skin cutaneous melanoma": "SKCM",
    "stomach adenocarcinoma": "STAD",
    "testicular germ cell tumor": "TGCT",
    "thymoma": "THYM",
    "thyroid carcinoma": "THCA",
    "uterine carcinosarcoma": "UCS",
    "uterine corpus endometrioid carcinoma": "UCEC",
    "uveal melanoma": "UVM",
}


def build_sample_labels(
    phenotype_tsv: Path = DATA_DIR / "phenotype.tsv",
    subtype_tsv: Path = DATA_DIR / "subtype.tsv",
    infiltration_csv: Path = Path("/Users/hh667/Downloads/infiltration_estimation_for_tcga.csv"),
) -> pd.DataFrame:
    """
    Returns a long-form DataFrame: (sample_id, label).

    A BRCA tumor of LumA subtype produces two rows: ('TCGA-...', 'BRCA') and
    ('TCGA-...', 'BRCA-LumA'). Only samples present in the infiltration CSV
    are kept (this is what TIMER3 actually has data for).
    """
    pheno = pd.read_csv(phenotype_tsv, sep="\t")
    pheno = pheno[pheno["sample_type"] == "Primary Tumor"].copy()
    pheno["disease_lower"] = pheno["_primary_disease"].str.lower()
    pheno["code"] = pheno["disease_lower"].map(DISEASE_TO_CODE)

    sub = pd.read_csv(subtype_tsv, sep="\t")[["sampleID", "Subtype_Selected"]]
    sub = sub.rename(columns={"sampleID": "sample"})
    pheno = pheno.merge(sub, on="sample", how="left")

    # Restrict to samples that actually appear in TIMER3's infiltration matrix
    infl_samples = set(pd.read_csv(infiltration_csv, usecols=["cell_type"])["cell_type"])
    pheno = pheno[pheno["sample"].isin(infl_samples)].copy()

    rows = []
    for _, r in pheno.iterrows():
        code = r["code"]
        if pd.isna(code):
            continue
        rows.append((r["sample"], code))
        # BRCA subtype overlay
        if code == "BRCA" and isinstance(r["Subtype_Selected"], str):
            sub_label = r["Subtype_Selected"]  # e.g. "BRCA.LumA"
            if sub_label.startswith("BRCA.") and not sub_label.endswith(".Normal"):
                rows.append((r["sample"], sub_label.replace(".", "-")))

    return pd.DataFrame(rows, columns=["sample", "label"])


if __name__ == "__main__":
    df = build_sample_labels()
    print(df.groupby("label").size().sort_index())
    print(f"\nTotal label rows: {len(df)}")
    print(f"Unique samples:   {df['sample'].nunique()}")
    print(f"Unique labels:    {df['label'].nunique()}")
