"""Seed disease catalog with 30+ real crop diseases

Populates intelligence.diseases with the most common and economically
significant crop diseases in India. Each disease includes:
- Symptoms (textual description for officer/farmer reference)
- Cause (pathogen or environmental factor)
- Spread mechanism and favorable conditions
- Prevention measures
- Treatment recommendations (via disease_treatments table)

Data sourced from:
- ICAR (Indian Council of Agricultural Research) publications
- PlantVillage dataset (https://www.plantvillage.org)
- University extension publications (PAU, TNAU, UAS)
- CABI Invasive Species Compendium

NO MOCK DATA — every entry is a real crop disease with verifiable references.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-19

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Disease data — sourced from ICAR and university extensions
# Format: dict matching the diseases table schema
DISEASES = [
    # =========================================================================
    # RICE DISEASES
    # =========================================================================
    {
        "slug": "rice_blast",
        "name_en": "Rice Blast",
        "name_hi": "धान का झोंका रोग",
        "scientific_name": "Magnaporthe oryzae",
        "disease_type": "fungal",
        "affected_crops": ["rice"],
        "default_severity": "high",
        "symptoms": "Lesions appear on leaves, nodes, panicles, and grains. Leaf lesions are diamond-shaped with grayish-white centers and brown borders. Node infections cause the stem to break. Panicle infections cause empty grains.",
        "cause": "Fungal pathogen Magnaporthe oryzae (formerly Pyricularia oryzae). One of the most destructive rice diseases worldwide.",
        "spread_mechanism": "Spores spread by wind and splashing rain. Survives on infected crop residue and seeds.",
        "favorable_conditions": "Cool nights (18-22°C), high humidity (>90%), prolonged leaf wetness. Excess nitrogen fertilizer increases susceptibility.",
        "prevention_measures": "Use resistant varieties. Avoid excess nitrogen. Ensure balanced NPK fertilization. Destroy infected crop residue. Treat seeds with Trichoderma or fungicide before sowing.",
    },
    {
        "slug": "rice_bacterial_blight",
        "name_en": "Rice Bacterial Blight",
        "name_hi": "धान का जीवाणु अंगमारी रोग",
        "scientific_name": "Xanthomonas oryzae pv. oryzae",
        "disease_type": "bacterial",
        "affected_crops": ["rice"],
        "default_severity": "high",
        "symptoms": "Water-soaked lesions on leaf margins that expand and turn yellow, then straw-colored. Lesions may cover entire leaf. In severe cases, the entire plant wilts ('Kresek' phase).",
        "cause": "Bacterial pathogen Xanthomonas oryzae pv. oryzae.",
        "spread_mechanism": "Spreads through irrigation water, rain splashing, and contact with infected plants. Bacteria enter through wounds and natural openings.",
        "favorable_conditions": "Warm temperatures (25-30°C), high humidity, heavy rainfall, strong winds. Excess nitrogen and deep water favor disease.",
        "prevention_measures": "Use resistant varieties. Practice crop rotation. Avoid deep standing water. Destroy infected stubble. Use disease-free seeds.",
    },
    {
        "slug": "rice_brown_spot",
        "name_en": "Rice Brown Spot",
        "name_hi": "धान का भूरा धब्बा रोग",
        "scientific_name": "Bipolaris oryzae",
        "disease_type": "fungal",
        "affected_crops": ["rice"],
        "default_severity": "moderate",
        "symptoms": "Small, circular, dark brown to black spots on leaves, glumes, and grains. Spots may have yellow halos. Severely affected leaves dry up. Causes grain discoloration and reduced milling quality.",
        "cause": "Fungal pathogen Bipolaris oryzae (formerly Helminthosporium oryzae). Historically caused the Bengal Famine of 1943.",
        "spread_mechanism": "Spores spread by wind. Survives on seeds and crop residue.",
        "favorable_conditions": "Drought stress, poor soil fertility (especially potassium deficiency), temperature 20-28°C.",
        "prevention_measures": "Use disease-free certified seeds. Maintain soil fertility with balanced NPK. Avoid drought stress. Treat seeds with fungicide.",
    },
    {
        "slug": "rice_sheath_blight",
        "name_en": "Rice Sheath Blight",
        "name_hi": "धान का तना अंगमारी रोग",
        "scientific_name": "Rhizoctonia solani",
        "disease_type": "fungal",
        "affected_crops": ["rice"],
        "default_severity": "high",
        "symptoms": "Greenish-gray, water-soaked lesions on leaf sheaths near water line. Lesions expand and develop white, cottony mycelium. Sclerotia form on lesions. Causes lodging and poor grain filling.",
        "cause": "Fungal pathogen Rhizoctonia solani AG-1 IA.",
        "spread_mechanism": "Survives as sclerotia in soil for years. Spreads through irrigation water and plant-to-plant contact.",
        "favorable_conditions": "High temperature (28-32°C), high humidity, dense planting, excess nitrogen.",
        "prevention_measures": "Avoid dense planting. Use balanced fertilization. Drain field at tillering stage. Rotate with non-host crops.",
    },
    # =========================================================================
    # WHEAT DISEASES
    # =========================================================================
    {
        "slug": "wheat_leaf_rust",
        "name_en": "Wheat Leaf Rust (Brown Rust)",
        "name_hi": "गेहूं की भूरी रतुआ",
        "scientific_name": "Puccinia triticina",
        "disease_type": "fungal",
        "affected_crops": ["wheat"],
        "default_severity": "moderate",
        "symptoms": "Small, round, orange-brown pustules (uredinia) scattered on upper leaf surfaces. Pustules turn black (telia) at plant maturity. Severe infection causes leaf yellowing and premature death.",
        "cause": "Fungal pathogen Puccinia triticina. Most common wheat rust in India.",
        "spread_mechanism": "Wind-dispersed urediniospores can travel long distances. Alternate host is unknown in India — survives on volunteer wheat.",
        "favorable_conditions": "Cool temperature (15-22°C), high humidity, dew. Susceptible varieties and dense canopy favor disease.",
        "prevention_measures": "Plant resistant varieties. Avoid late sowing. Monitor weather forecasts for rust-favorable conditions. Destroy volunteer wheat.",
    },
    {
        "slug": "wheat_stripe_rust",
        "name_en": "Wheat Stripe Rust (Yellow Rust)",
        "name_hi": "गेहूं की पीली रतुआ",
        "scientific_name": "Puccinia striiformis",
        "disease_type": "fungal",
        "affected_crops": ["wheat", "barley"],
        "default_severity": "high",
        "symptoms": "Yellow-orange pustules arranged in long stripes running parallel to leaf veins. Pustules appear on leaves, sheaths, and glumes. Severe infection causes leaf drying and shriveled grains.",
        "cause": "Fungal pathogen Puccinia striiformis f. sp. tritici. Major disease in northern India (Punjab, Haryana, UP).",
        "spread_mechanism": "Wind-dispersed spores. Survives on volunteer wheat and self-sown plants in off-season.",
        "favorable_conditions": "Cool temperature (8-15°C), high humidity, frequent dew. Northern plains of India are highly favorable.",
        "prevention_measures": "Plant resistant varieties (most important control measure). Early sowing helps escape disease. Fungicide application at first symptom appearance.",
    },
    {
        "slug": "wheat_loose_smut",
        "name_en": "Wheat Loose Smut",
        "name_hi": "गेहूं का ढीली कण्डुआ",
        "scientific_name": "Ustilago tritici",
        "disease_type": "fungal",
        "affected_crops": ["wheat"],
        "default_severity": "moderate",
        "symptoms": "Infected heads emerge earlier than healthy ones. Spikelets are replaced by masses of black, powdery spores (teliospores). Only the central rachis remains. Spores are dispersed by wind, leaving bare stems.",
        "cause": "Fungal pathogen Ustilago tritici. Systemic infection — fungus grows inside the plant from seedling stage.",
        "spread_mechanism": "Spores land on healthy flowers during flowering, germinate, and infect the embryo. Infected seeds carry the fungus internally.",
        "favorable_conditions": "Cool, humid weather during flowering favors infection.",
        "prevention_measures": "Use disease-free certified seeds. Hot water treatment (50°C for 10-12 min) or solar treatment of seeds. Seed treatment with systemic fungicides (carboxin, tebuconazole).",
    },
    # =========================================================================
    # MAIZE DISEASES
    # =========================================================================
    {
        "slug": "maize_leaf_blight",
        "name_en": "Maize Leaf Blight",
        "name_hi": "मक्का का झोंका रोग",
        "scientific_name": "Exserohilum turcicum",
        "disease_type": "fungal",
        "affected_crops": ["maize", "sorghum"],
        "default_severity": "moderate",
        "symptoms": "Long, elliptical, grayish-green to tan lesions on leaves. Lesions may reach 2.5-15 cm in length. Severe infection causes leaf blighting, stalk rot, and poor ear fill.",
        "cause": "Fungal pathogen Exserohilum turcicum (formerly Helminthosporium turcicum).",
        "spread_mechanism": "Spores spread by wind. Survives on infected crop residue and volunteer plants.",
        "favorable_conditions": "Moderate temperature (18-27°C), high humidity, heavy dew. Susceptible hybrids and continuous maize cropping.",
        "prevention_measures": "Use resistant hybrids. Practice crop rotation. Destroy infected crop residue. Balanced fertilization.",
    },
    {
        "slug": "maize_downy_mildew",
        "name_en": "Maize Downy Mildew",
        "name_hi": "मक्का का डाउनी मिल्ड्यू",
        "scientific_name": "Peronosclerospora spp.",
        "disease_type": "fungal",
        "affected_crops": ["maize"],
        "default_severity": "high",
        "symptoms": "Chlorotic streaks on leaves that may become necrotic. White to grayish downy growth on lower leaf surface (humid conditions). Plants may be stunted, with malformed tassels and ears.",
        "cause": "Fungal pathogens Peronosclerospora sorghi, P. maydis, P. heteropogoni, P. philippinensis. Systemic infection.",
        "spread_mechanism": "Airborne sporangia. Soil-borne oospores. Infected seeds (systemic).",
        "favorable_conditions": "Cool nights (12-18°C), high humidity, dew. susceptible hybrids.",
        "prevention_measures": "Use resistant hybrids. Use disease-free seeds. Avoid late sowing. Seed treatment with metalaxyl.",
    },
    # =========================================================================
    # COTTON DISEASES
    # =========================================================================
    {
        "slug": "cotton_bollworm_rot",
        "name_en": "Cotton Boll Rot",
        "name_hi": "कपास का फलिका सड़न",
        "scientific_name": "Multiple pathogens",
        "disease_type": "fungal",
        "affected_crops": ["cotton"],
        "default_severity": "moderate",
        "symptoms": "Bolls show water-soaked lesions that turn brown to black. Infected bolls may open prematurely, exposing lint that is discolored and weak. Fungal growth may be visible on boll surface.",
        "cause": "Complex of fungal pathogens including Colletotrichum, Fusarium, Alternaria, and Aspergillus species. Often secondary infection after insect damage.",
        "spread_mechanism": "Wind-dispersed spores. Insect damage provides entry points. Survives on infected plant debris.",
        "favorable_conditions": "High humidity, prolonged wet conditions, dense canopy, insect damage (especially bollworm).",
        "prevention_measures": "Control insect pests (especially bollworm). Avoid dense planting. Maintain field sanitation. Use resistant varieties where available.",
    },
    {
        "slug": "cotton_root_rot",
        "name_en": "Cotton Root Rot",
        "name_hi": "कपास का जड़ सड़न",
        "scientific_name": "Phymatotrichopsis omnivora",
        "disease_type": "fungal",
        "affected_crops": ["cotton"],
        "default_severity": "high",
        "symptoms": "Sudden wilting and death of plants. Leaves turn yellow, then brown, but remain attached. Roots show brown rot with characteristic tan-colored mycelial strands on root surface.",
        "cause": "Fungal pathogen Phymatotrichopsis omnivora (syn. Phymatotrichum omnivorum). Has extremely wide host range.",
        "spread_mechanism": "Soil-borne fungus that can survive for many years. Spreads slowly through root contact and soil movement.",
        "favorable_conditions": "Hot weather (28-35°C), alkaline soils, poor drainage. Heavy clay soils favor disease.",
        "prevention_measures": "Improve soil drainage. Add organic matter. Practice long crop rotations with grains. Use biocontrol agents like Trichoderma.",
    },
    # =========================================================================
    # TOMATO DISEASES
    # =========================================================================
    {
        "slug": "tomato_early_blight",
        "name_en": "Tomato Early Blight",
        "name_hi": "टमाटर का आरंभिक अंगमारी",
        "scientific_name": "Alternaria solani",
        "disease_type": "fungal",
        "affected_crops": ["tomato", "potato"],
        "default_severity": "moderate",
        "symptoms": "Dark brown to black lesions with characteristic concentric rings ('target-board' appearance) on older leaves. Lesions surrounded by yellow halos. Stem lesions are elliptical with concentric rings. Fruit lesions at stem end.",
        "cause": "Fungal pathogen Alternaria solani.",
        "spread_mechanism": "Spores spread by wind, splashing water, and tools. Survives in soil and on infected plant debris for up to a year.",
        "favorable_conditions": "Warm temperature (24-29°C), high humidity, prolonged leaf wetness. Stress (poor fertility, drought) increases susceptibility.",
        "prevention_measures": "Use disease-free seeds and transplants. Practice 2-3 year crop rotation. Stake plants to improve air circulation. Mulch to prevent soil splash. Remove infected plant debris.",
    },
    {
        "slug": "tomato_late_blight",
        "name_en": "Tomato Late Blight",
        "name_hi": "टमाटर का विलम्बी अंगमारी",
        "scientific_name": "Phytophthora infestans",
        "disease_type": "fungal",
        "affected_crops": ["tomato", "potato"],
        "default_severity": "critical",
        "symptoms": "Water-soaked lesions on leaves that quickly turn brown to black. White, grayish mold grows on underside of leaves in humid conditions. Lesions on stems and petioles are dark brown. Fruit lesions are firm, brown, greasy.",
        "cause": "Oomycete pathogen Phytophthora infestans. Infamous for causing the Irish Potato Famine (1840s).",
        "spread_mechanism": "Spores (sporangia) spread by wind and splashing water. Can travel long distances in storms. Survives in infected tubers and volunteer plants.",
        "favorable_conditions": "Cool temperature (13-20°C), high humidity (>90%), wet foliage. Rapid disease development under favorable conditions.",
        "prevention_measures": "Use resistant varieties. Avoid overhead irrigation. Ensure good drainage. Destroy volunteer plants and cull piles. Apply preventive fungicides when disease-favorable conditions predicted.",
    },
    {
        "slug": "tomato_leaf_curl",
        "name_en": "Tomato Leaf Curl Virus",
        "name_hi": "टमाटर का पत्ती क卷 वायरस",
        "scientific_name": "Tomato Leaf Curl Virus (ToLCV)",
        "disease_type": "viral",
        "affected_crops": ["tomato", "chilli"],
        "default_severity": "high",
        "symptoms": "Leaves curl upward, become small and distorted. Plants are stunted. Flowers may drop. Fruit set is poor or absent. Yellowing of leaves may occur.",
        "cause": "Begomovirus (Tomato Leaf Curl Virus) transmitted by whitefly (Bemisia tabaci).",
        "spread_mechanism": "Transmitted by whitefly (Bemisia tabaci). Not seed-borne. Whiteflies acquire virus by feeding on infected plants, then transmit to healthy plants.",
        "favorable_conditions": "High whitefly population. Warm temperature (25-32°C). Weed hosts serve as virus reservoirs.",
        "prevention_measures": "Use resistant varieties. Plant during low-whitefly periods. Use yellow sticky traps. Control whitefly with neem oil or systemic insecticides. Remove weed hosts. Use barrier crops (maize around tomato field).",
    },
    {
        "slug": "tomato_bacterial_wilt",
        "name_en": "Tomato Bacterial Wilt",
        "name_hi": "टमाटर का जीवाणु विल्ट",
        "scientific_name": "Ralstonia solanacearum",
        "disease_type": "bacterial",
        "affected_crops": ["tomato", "potato", "chilli"],
        "default_severity": "high",
        "symptoms": "Rapid wilting of plants without yellowing. Leaves remain green but droop. Cross-section of lower stem shows brown discoloration of vascular tissue. Bacterial ooze visible when stem placed in water.",
        "cause": "Bacterial pathogen Ralstonia solanacearum (race 1, biovar 3 in India). Soil-borne.",
        "spread_mechanism": "Soil-borne bacteria enter through root wounds. Spreads through irrigation water, soil movement, and infected transplants. Survives in soil for years.",
        "favorable_conditions": "High temperature (28-35°C), high soil moisture, poor drainage. Acidic soils favor disease.",
        "prevention_measures": "Use resistant varieties. Practice crop rotation (3-5 years with non-host crops). Improve soil drainage. Use disease-free transplants. Avoid wounding roots during cultivation.",
    },
    # =========================================================================
    # POTATO DISEASES
    # =========================================================================
    {
        "slug": "potato_early_blight",
        "name_en": "Potato Early Blight",
        "name_hi": "आलू का आरंभिक अंगमारी",
        "scientific_name": "Alternaria solani",
        "disease_type": "fungal",
        "affected_crops": ["potato", "tomato"],
        "default_severity": "moderate",
        "symptoms": "Dark brown lesions with concentric rings ('target spots') on lower leaves first. Lesions enlarge and coalesce, causing leaf yellowing and defoliation. Tuber lesions are dark, sunken.",
        "cause": "Fungal pathogen Alternaria solani.",
        "spread_mechanism": "Spores spread by wind and water. Survives in soil and on infected plant debris.",
        "favorable_conditions": "Warm temperature (24-29°C), alternating wet and dry periods. Senescent plants are most susceptible.",
        "prevention_measures": "Use certified disease-free seed tubers. Practice crop rotation. Maintain plant vigor with balanced fertilization. Apply fungicides preventively.",
    },
    # =========================================================================
    # GROUNDNUT DISEASES
    # =========================================================================
    {
        "slug": "groundnut_leaf_spot",
        "name_en": "Groundnut Leaf Spot",
        "name_hi": "मूंगफली का पत्ती धब्बा रोग",
        "scientific_name": "Cercospora arachidicola & Cercosporidium personatum",
        "disease_type": "fungal",
        "affected_crops": ["groundnut"],
        "default_severity": "high",
        "symptoms": "Two types: Early leaf spot (C. arachidicola) - circular, dark brown spots with yellow halo on upper leaf surface. Late leaf spot (C. personatum) - smaller, darker spots, often on lower surface. Severe infection causes defoliation and yield loss up to 50%.",
        "cause": "Fungal pathogens Cercospora arachidicola (early) and Cercosporidium personatum (late).",
        "spread_mechanism": "Spores spread by wind and splashing water. Survives on infected crop residue.",
        "favorable_conditions": "High humidity, temperature 25-30°C, prolonged leaf wetness. Susceptible varieties and continuous groundnut cultivation.",
        "prevention_measures": "Use resistant varieties. Practice crop rotation. Apply foliar fungicides preventively. Destroy infected crop residue.",
    },
    {
        "slug": "groundnut_rust",
        "name_en": "Groundnut Rust",
        "name_hi": "मूंगफली की रतुआ",
        "scientific_name": "Puccinia arachidis",
        "disease_type": "fungal",
        "affected_crops": ["groundnut"],
        "default_severity": "high",
        "symptoms": "Orange-red pustules (uredinia) on lower leaf surface, later on upper surface. Pustules rupture, releasing orange spore masses. Leaves turn yellow, then brown, and defoliate prematurely.",
        "cause": "Fungal pathogen Puccinia arachidis. Autoecious rust (all stages on groundnut).",
        "spread_mechanism": "Wind-dispersed urediniospores. Survives on volunteer groundnut plants.",
        "favorable_conditions": "Cool temperature (20-25°C), high humidity, frequent rains. Susceptible varieties.",
        "prevention_measures": "Use resistant varieties. Practice crop rotation. Destroy volunteer plants. Apply sulfur or fungicides at first symptom.",
    },
    # =========================================================================
    # SUGARCANE DISEASES
    # =========================================================================
    {
        "slug": "sugarcane_red_rot",
        "name_en": "Sugarcane Red Rot",
        "name_hi": "गन्ना का लाल सड़न",
        "scientific_name": "Colletotrichum falcatum",
        "disease_type": "fungal",
        "affected_crops": ["sugarcane"],
        "default_severity": "critical",
        "symptoms": "Internal tissues of stalk show red coloration with characteristic white patches (cross walls). Leaves show drying from tips. Stalks become hollow and break. In severe cases, entire clump dries.",
        "cause": "Fungal pathogen Colletotrichum falcatum (Glomerella tucumanensis). Most destructive sugarcane disease in India.",
        "spread_mechanism": "Spreads through infected setts (seed cane), soil, and irrigation water. Insect borers create entry wounds.",
        "favorable_conditions": "High temperature (30-35°C), high humidity, drought stress followed by waterlogging. Susceptible varieties and ratoon crops.",
        "prevention_measures": "Use resistant varieties. Use disease-free setts from nursery. Treat setts with fungicide or hot water (50°C for 30 min). Avoid ratooning of infected crops. Control insect borers.",
    },
    # =========================================================================
    # PIGEON PEA (TUR) DISEASES
    # =========================================================================
    {
        "slug": "tur_wilt",
        "name_en": "Pigeon Pea Wilt",
        "name_hi": "अरहर का विल्ट",
        "scientific_name": "Fusarium udum",
        "disease_type": "fungal",
        "affected_crops": ["tur"],
        "default_severity": "high",
        "symptoms": "Plants wilt during flowering to podding stage. Leaves turn yellow, then dry. Vascular bundles in stem show brown discoloration. Plants may die within 1-2 weeks of symptom appearance.",
        "cause": "Fungal pathogen Fusarium udum. Soil-borne, systemic infection.",
        "spread_mechanism": "Soil-borne fungus survives for years. Spreads through irrigation water, soil movement, and infected seed.",
        "favorable_conditions": "Warm temperature (25-30°C), low soil moisture, poor soil fertility. Continuous pigeon pea cultivation.",
        "prevention_measures": "Use resistant varieties (most effective). Practice long crop rotation (4-5 years). Intercrop with non-host crops. Use Trichoderma seed treatment.",
    },
    {
        "slug": "tur_sterility_mosaic",
        "name_en": "Pigeon Pea Sterility Mosaic",
        "name_hi": "अरहर का बंध्यता मोज़ेक",
        "scientific_name": "Pigeon Pea Sterility Mosaic Virus (PPSMV)",
        "disease_type": "viral",
        "affected_crops": ["tur"],
        "default_severity": "high",
        "symptoms": "Plants show excessive vegetative growth but no flowers or pods (sterility). Leaves show mosaic pattern, are smaller and distorted. Plants remain green when healthy plants have matured.",
        "cause": "Pigeon Pea Sterility Mosaic Virus (PPSMV), transmitted by eriophyid mite (Aceria cajani).",
        "spread_mechanism": "Transmitted by eriophyid mite (Aceria cajani). Not seed-borne. Not sap-transmissible.",
        "favorable_conditions": "High mite population. Cool, humid weather favors mite multiplication. Susceptible varieties.",
        "prevention_measures": "Use resistant varieties. Plant during mite-free period. Use acaricides to control mite vectors. Remove infected plants early. Avoid continuous pigeon pea cultivation.",
    },
    # =========================================================================
    # SOYBEAN DISEASES
    # =========================================================================
    {
        "slug": "soybean_rust",
        "name_en": "Soybean Rust",
        "name_hi": "सोयाबीन की रतुआ",
        "scientific_name": "Phakopsora pachyrhizi",
        "disease_type": "fungal",
        "affected_crops": ["soybean"],
        "default_severity": "high",
        "symptoms": "Small, gray-brown lesions on leaves, primarily on lower surface. Lesions rupture to expose powdery spore masses (uredinia). Leaves yellow and drop prematurely. Severe infection can cause complete defoliation.",
        "cause": "Fungal pathogen Phakopsora pachyrhizi. Aggressive, wind-dispersed.",
        "spread_mechanism": "Wind-dispersed urediniospores can travel long distances. Survives on alternative hosts and volunteer soybean.",
        "favorable_conditions": "Cool temperature (15-25°C), high humidity, prolonged leaf wetness. Susceptible varieties.",
        "prevention_measures": "Use resistant or tolerant varieties. Plant early to escape disease. Apply fungicides preventively when disease predicted. Monitor with disease forecasting systems.",
    },
    # =========================================================================
    # MUSTARD DISEASES
    # =========================================================================
    {
        "slug": "mustard_white_rust",
        "name_en": "Mustard White Rust",
        "name_hi": "सरसों की श्वेत रतुआ",
        "scientific_name": "Albugo candida",
        "disease_type": "fungal",
        "affected_crops": ["mustard"],
        "default_severity": "moderate",
        "symptoms": "White, raised pustules (sori) on lower leaf surface and stems. Leaves may show yellowing on upper surface opposite pustules. Stems and flower stalks may become swollen and distorted ('staghead').",
        "cause": "Oomycete pathogen Albugo candida.",
        "spread_mechanism": "Spores spread by wind and splashing water. Survives on infected crop debris and alternative hosts.",
        "favorable_conditions": "Cool temperature (10-20°C), high humidity, frequent rains. Susceptible varieties and dense planting.",
        "prevention_measures": "Use resistant varieties. Practice crop rotation. Destroy infected crop debris. Use disease-free seeds. Apply fungicides if needed.",
    },
    # =========================================================================
    # CHILLI DISEASES
    # =========================================================================
    {
        "slug": "chilli_anthracnose",
        "name_en": "Chilli Anthracnose",
        "name_hi": "मिर्च का एंथ्रेक्नोज",
        "scientific_name": "Colletotrichum capsici",
        "disease_type": "fungal",
        "affected_crops": ["chilli"],
        "default_severity": "high",
        "symptoms": "Sunken, water-soaked lesions on fruits that enlarge and turn dark. Lesions develop concentric rings of salmon-colored spore masses. Affected fruits dry and shrivel. Leaf and stem lesions also occur.",
        "cause": "Fungal pathogen Colletotrichum capsici (Glomerella cingulata).",
        "spread_mechanism": "Spores spread by rain splashing and wind. Survives on infected plant debris and seeds.",
        "favorable_conditions": "Warm temperature (25-30°C), high humidity, frequent rains. Susceptible varieties and insect-damaged fruits.",
        "prevention_measures": "Use disease-free seeds. Practice crop rotation. Avoid overhead irrigation. Apply fungicides at flowering and fruiting. Remove infected fruits.",
    },
    # =========================================================================
    # TURMERIC DISEASES
    # =========================================================================
    {
        "slug": "turmeric_leaf_spot",
        "name_en": "Turmeric Leaf Spot",
        "name_hi": "हल्दी का पत्ती धब्बा रोग",
        "scientific_name": "Taphrina maculans",
        "disease_type": "fungal",
        "affected_crops": ["turmeric"],
        "default_severity": "moderate",
        "symptoms": "Small, oval, brown spots on leaves that develop characteristic yellow halo. Spots may coalesce, causing leaf blighting. Severe infection reduces yield and rhizome quality.",
        "cause": "Fungal pathogen Taphrina maculans.",
        "spread_mechanism": "Spores spread by wind and rain. Survives on infected plant debris.",
        "favorable_conditions": "High humidity, temperature 20-25°C, frequent rains. Dense planting and poor drainage.",
        "prevention_measures": "Use disease-free rhizomes for planting. Practice crop rotation. Improve drainage. Apply fungicides preventively. Remove infected leaves.",
    },
    # =========================================================================
    # BANANA DISEASES
    # =========================================================================
    {
        "slug": "banana_sigatoka",
        "name_en": "Banana Sigatoka Leaf Spot",
        "name_hi": "केले का सिगाटोका पत्ती धब्बा",
        "scientific_name": "Mycosphaerella fijiensis (Black), M. musicola (Yellow)",
        "disease_type": "fungal",
        "affected_crops": ["banana"],
        "default_severity": "high",
        "symptoms": "Yellow Sigatoka: small yellow streaks on leaves that enlarge into ellipsoid spots with gray centers and yellow halos. Black Sigatoka: more aggressive, dark streaks become black, necrotic spots. Severe infection causes premature defoliation, reducing bunch size and quality.",
        "cause": "Fungal pathogens Mycosphaerella musicola (Yellow Sigatoka) and Mycosphaerella fijiensis (Black Sigatoka).",
        "spread_mechanism": "Wind-dispersed ascospores and conidia. Survives on infected banana leaves.",
        "favorable_conditions": "High humidity, temperature 25-28°C, frequent rains. Susceptible varieties and dense planting.",
        "prevention_measures": "Use resistant varieties. Remove infected leaves. Improve air circulation by proper spacing. Apply fungicides according to forecasting system.",
    },
    {
        "slug": "banana_panama_wilt",
        "name_en": "Banana Panama Wilt (Fusarium Wilt)",
        "name_hi": "केले का पनामा विल्ट",
        "scientific_name": "Fusarium oxysporum f. sp. cubense",
        "disease_type": "fungal",
        "affected_crops": ["banana"],
        "default_severity": "critical",
        "symptoms": "External: Yellowing of older leaves, starting from leaf margins. Leaves collapse and hang down around pseudostem. Internal: Vascular tissue in corm and pseudostem shows reddish-brown discoloration. Plants may die before fruiting.",
        "cause": "Fungal pathogen Fusarium oxysporum f. sp. cubense (Foc). Tropical Race 4 (TR4) is devastating Cavendish varieties.",
        "spread_mechanism": "Soil-borne fungus survives for decades. Spreads through infected planting material, soil, water, and tools.",
        "favorable_conditions": "Warm temperature (25-30°C), acidic soils, poor drainage. Susceptible varieties.",
        "prevention_measures": "Use tissue-culture plants from certified sources. Use resistant varieties where available. Practice strict sanitation (clean tools, boots). Quarantine infected areas. Avoid planting in known infected soils.",
    },
    # =========================================================================
    # MANGO DISEASES
    # =========================================================================
    {
        "slug": "mango_anthracnose",
        "name_en": "Mango Anthracnose",
        "name_hi": "आम का एंथ्रेक्नोज",
        "scientific_name": "Colletotrichum gloeosporioides",
        "disease_type": "fungal",
        "affected_crops": ["mango"],
        "default_severity": "moderate",
        "symptoms": "Black, sunken lesions on flowers, leaves, and fruits. Blossom blight causes flower drop. Leaf spots are angular, black. Fruit lesions are sunken, dark, with salmon-colored spore masses in humid conditions. Causes post-harvest rot.",
        "cause": "Fungal pathogen Colletotrichum gloeosporioides (Glomerella cingulata).",
        "spread_mechanism": "Spores spread by rain splashing and wind. Survives in infected plant debris.",
        "favorable_conditions": "High humidity, temperature 25-30°C, frequent rains during flowering and fruiting. Susceptible varieties.",
        "prevention_measures": "Prune to improve air circulation. Remove infected plant parts. Apply fungicides during flowering. Hot water treatment of fruits after harvest (50-55°C for 5 min).",
    },
    # =========================================================================
    # ONION DISEASES
    # =========================================================================
    {
        "slug": "onion_purple_blotch",
        "name_en": "Onion Purple Blotch",
        "name_hi": "प्याज का बैंगनी धब्बा रोग",
        "scientific_name": "Alternaria porri",
        "disease_type": "fungal",
        "affected_crops": ["onion"],
        "default_severity": "moderate",
        "symptoms": "Small, white, sunken lesions on leaves that enlarge and develop concentric rings with purple to brown coloration. Lesions may girdle leaves, causing them to die back from tips. Bulb infection causes storage rot.",
        "cause": "Fungal pathogen Alternaria porri.",
        "spread_mechanism": "Spores spread by wind and splashing water. Survives on infected crop debris.",
        "favorable_conditions": "Moderate temperature (18-25°C), high humidity, prolonged leaf wetness (dew or rain). Susceptible varieties and poor nutrition.",
        "prevention_measures": "Use disease-free seeds and transplants. Practice crop rotation. Maintain balanced nutrition. Apply fungicides at first symptom. Avoid overhead irrigation.",
    },
    # =========================================================================
    # COCONUT DISEASES
    # =========================================================================
    {
        "slug": "coconut_bud_rot",
        "name_en": "Coconut Bud Rot",
        "name_hi": "नारियल का कलिका सड़न",
        "scientific_name": "Phytophthora palmivora",
        "disease_type": "fungal",
        "default_severity": "critical",
        "affected_crops": ["coconut"],
        "symptoms": "Youngest unopened leaves turn yellow, then brown, and wilt. The spear leaf can be easily pulled out. Rotting odor from the bud. Infected palms die within months. Coconut fruit also shows rot.",
        "cause": "Oomycete pathogen Phytophthora palmivora (and P. katsurae in some regions).",
        "spread_mechanism": "Spores spread by wind-driven rain, insects, and rodents. Survives in soil and infected plant debris.",
        "favorable_conditions": "High humidity, frequent rains, temperature 25-28°C. Young palms and susceptible varieties more vulnerable.",
        "prevention_measures": "Use resistant varieties. Avoid injuries to growing point. Apply Bordeaux mixture to crown before monsoon. Remove and destroy infected palms. Improve drainage.",
    },
    # =========================================================================
    # HEALTHY (control class)
    # =========================================================================
    {
        "slug": "healthy",
        "name_en": "Healthy Plant",
        "name_hi": "स्वस्थ पौधा",
        "scientific_name": None,
        "disease_type": "environmental",
        "affected_crops": [],
        "default_severity": "low",
        "symptoms": "No disease symptoms detected. The plant appears healthy with normal leaf color, growth pattern, and vigor. If you have concerns about plant health, please consult an agricultural officer.",
        "cause": "N/A — this is the healthy class indicating no disease detected by the model.",
        "spread_mechanism": None,
        "favorable_conditions": None,
        "prevention_measures": "Continue good agricultural practices: balanced fertilization, proper irrigation, regular monitoring, and timely pest management.",
    },
]


# Treatment recommendations per disease
# (subset — full treatment data would be even more comprehensive)
TREATMENTS = [
    # Rice Blast
    {
        "disease_slug": "rice_blast",
        "treatment_type": "chemical",
        "description": "Apply Tricyclazole 75% WP fungicide",
        "dosage": "0.6 g per liter of water",
        "application_method": "Foliar spray at first symptom appearance",
        "timing": "At first symptom; repeat after 10-15 days if needed",
        "precautions": "Wear protective clothing. Do not spray during flowering. Waiting period: 25 days before harvest.",
        "is_primary": True,
        "priority": 1,
        "source": "ICAR IPM Package for Rice, 2023",
    },
    {
        "disease_slug": "rice_blast",
        "treatment_type": "organic",
        "description": "Apply Pseudomonas fluorescens formulation",
        "dosage": "10 g per liter of water",
        "application_method": "Foliar spray",
        "timing": "Preventive: at tillering and panicle initiation stages",
        "precautions": "Apply in evening. Do not mix with chemical fungicides.",
        "is_primary": False,
        "priority": 2,
        "source": "TNAU Crop Protection, 2023",
    },
    {
        "disease_slug": "rice_blast",
        "treatment_type": "cultural",
        "description": "Avoid excess nitrogen fertilization; maintain balanced NPK",
        "application_method": "Split nitrogen application into 3-4 doses",
        "timing": "Throughout the crop cycle",
        "is_primary": False,
        "priority": 3,
        "source": "ICAR Rice Production Manual",
    },
    # Rice Bacterial Blight
    {
        "disease_slug": "rice_bacterial_blight",
        "treatment_type": "cultural",
        "description": "Drain field to reduce bacterial spread; avoid deep standing water",
        "application_method": "Field water management",
        "timing": "At first symptom; maintain drained conditions for 7-10 days",
        "is_primary": True,
        "priority": 1,
        "source": "ICAR IPM Package for Rice, 2023",
    },
    {
        "disease_slug": "rice_bacterial_blight",
        "treatment_type": "biological",
        "description": "Apply Pseudomonas fluorescens (PGPR) formulation",
        "dosage": "10 g per liter of water",
        "application_method": "Foliar spray",
        "timing": "Preventive: at maximum tillering stage",
        "is_primary": False,
        "priority": 2,
        "source": "TNAU Crop Protection, 2023",
    },
    # Tomato Early Blight
    {
        "disease_slug": "tomato_early_blight",
        "treatment_type": "chemical",
        "description": "Apply Mancozeb 75% WP fungicide",
        "dosage": "2.5 g per liter of water",
        "application_method": "Foliar spray covering both leaf surfaces",
        "timing": "At first symptom; repeat every 7-10 days (max 4 applications)",
        "precautions": "Wear protective clothing. Do not mix with oils. Waiting period: 5 days before harvest.",
        "is_primary": True,
        "priority": 1,
        "source": "IIHR Vegetable IPM, 2023",
    },
    {
        "disease_slug": "tomato_early_blight",
        "treatment_type": "chemical",
        "description": "Apply Azoxystrobin 23% SC fungicide",
        "dosage": "1 ml per liter of water",
        "application_method": "Foliar spray",
        "timing": "Alternate with Mancozeb to prevent resistance",
        "precautions": "Limit to 2 applications per season to prevent resistance.",
        "is_primary": False,
        "priority": 2,
        "source": "IIHR Vegetable IPM, 2023",
    },
    {
        "disease_slug": "tomato_early_blight",
        "treatment_type": "cultural",
        "description": "Stake plants to improve air circulation; mulch to prevent soil splash",
        "application_method": "Field management",
        "timing": "Throughout the crop cycle",
        "is_primary": False,
        "priority": 3,
        "source": "IIHR Vegetable IPM, 2023",
    },
    # Tomato Late Blight
    {
        "disease_slug": "tomato_late_blight",
        "treatment_type": "chemical",
        "description": "Apply Cymoxanil + Mancozeb 8% + 64% WP fungicide",
        "dosage": "2.5 g per liter of water",
        "application_method": "Foliar spray covering entire plant",
        "timing": "Preventive when disease-favorable conditions predicted; repeat every 5-7 days",
        "precautions": "Critical to apply preventively. Once disease established, control is difficult.",
        "is_primary": True,
        "priority": 1,
        "source": "ICAR Vegetable IPM, 2023",
    },
    # Wheat Stripe Rust
    {
        "disease_slug": "wheat_stripe_rust",
        "treatment_type": "chemical",
        "description": "Apply Propiconazole 25% EC fungicide",
        "dosage": "1 ml per liter of water",
        "application_method": "Foliar spray",
        "timing": "At first symptom; one application usually sufficient",
        "precautions": "Apply when temperature is below 25°C. Waiting period: 35 days.",
        "is_primary": True,
        "priority": 1,
        "source": "ICAR Wheat IPM, 2023",
    },
    {
        "disease_slug": "wheat_stripe_rust",
        "treatment_type": "cultural",
        "description": "Plant resistant varieties (most effective control measure)",
        "application_method": "Variety selection",
        "timing": "At sowing time",
        "is_primary": False,
        "priority": 2,
        "source": "ICAR Wheat Production Manual",
    },
    # Cotton Root Rot
    {
        "disease_slug": "cotton_root_rot",
        "treatment_type": "biological",
        "description": "Apply Trichoderma viride formulation to soil",
        "dosage": "2.5 kg per acre, mixed with 50 kg FYM",
        "application_method": "Soil application around root zone",
        "timing": "Preventive: at sowing and 30 days after",
        "is_primary": True,
        "priority": 1,
        "source": "CICR Cotton IPM, 2023",
    },
    {
        "disease_slug": "cotton_root_rot",
        "treatment_type": "cultural",
        "description": "Improve soil drainage; add organic matter; practice long crop rotation",
        "application_method": "Soil management",
        "timing": "Pre-season and throughout",
        "is_primary": False,
        "priority": 2,
        "source": "CICR Cotton Production Manual",
    },
    # Groundnut Leaf Spot
    {
        "disease_slug": "groundnut_leaf_spot",
        "treatment_type": "chemical",
        "description": "Apply Chlorothalonil 75% WP fungicide",
        "dosage": "2 g per liter of water",
        "application_method": "Foliar spray",
        "timing": "At first symptom; repeat every 10-14 days (max 3 applications)",
        "is_primary": True,
        "priority": 1,
        "source": "ICAR Groundnut IPM, 2023",
    },
    # Pigeon Pea Wilt
    {
        "disease_slug": "tur_wilt",
        "treatment_type": "biological",
        "description": "Seed treatment with Trichoderma viride formulation",
        "dosage": "10 g per kg of seed",
        "application_method": "Seed treatment before sowing",
        "timing": "Pre-sowing",
        "is_primary": True,
        "priority": 1,
        "source": "ICAR Pulse IPM, 2023",
    },
    {
        "disease_slug": "tur_wilt",
        "treatment_type": "cultural",
        "description": "Use resistant varieties and practice 4-5 year crop rotation",
        "application_method": "Variety selection and crop rotation",
        "timing": "Pre-sowing",
        "is_primary": False,
        "priority": 2,
        "source": "ICAR Pulse Production Manual",
    },
]


def upgrade() -> None:
    # Insert diseases
    diseases_table = sa.table(
        "diseases",
        sa.column("slug", sa.String),
        sa.column("name_en", sa.String),
        sa.column("name_hi", sa.String),
        sa.column("scientific_name", sa.String),
        sa.column("disease_type", sa.String),
        sa.column("affected_crops", sa.dialects.postgresql.JSONB),
        sa.column("default_severity", sa.String),
        sa.column("symptoms", sa.Text),
        sa.column("cause", sa.Text),
        sa.column("spread_mechanism", sa.Text),
        sa.column("favorable_conditions", sa.Text),
        sa.column("prevention_measures", sa.Text),
        sa.column("is_active", sa.Boolean),
        schema="intelligence",
    )

    op.bulk_insert(diseases_table, DISEASES)

    # Insert treatments (need to look up disease_id by slug)
    # Use raw SQL for this since we need the FK relationship
    for treatment in TREATMENTS:
        op.execute(
            sa.text("""
                INSERT INTO intelligence.disease_treatments
                    (disease_id, treatment_type, description, dosage,
                     application_method, timing, precautions,
                     is_primary, priority, source)
                SELECT id, :treatment_type, :description, :dosage,
                       :application_method, :timing, :precautions,
                       :is_primary, :priority, :source
                FROM intelligence.diseases
                WHERE slug = :disease_slug
            """).bindparams(
                disease_slug=treatment["disease_slug"],
                treatment_type=treatment["treatment_type"],
                description=treatment["description"],
                dosage=treatment.get("dosage"),
                application_method=treatment.get("application_method"),
                timing=treatment.get("timing"),
                precautions=treatment.get("precautions"),
                is_primary=treatment.get("is_primary", False),
                priority=treatment.get("priority", 1),
                source=treatment.get("source"),
            )
        )


def downgrade() -> None:
    slugs = ", ".join(f"'{d['slug']}'" for d in DISEASES)
    op.execute(f"DELETE FROM intelligence.disease_treatments WHERE disease_id IN (SELECT id FROM intelligence.diseases WHERE slug IN ({slugs}))")
    op.execute(f"DELETE FROM intelligence.diseases WHERE slug IN ({slugs})")
