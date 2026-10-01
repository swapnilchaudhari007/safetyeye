"""Multilingual alert text (spoken on the site PA / shown on dashboard)."""

MESSAGES = {
    "en": {
        "no_helmet": {"title": "No helmet", "say": "Attention: worker without a safety helmet. Please wear your helmet now."},
        "no_vest": {"title": "No safety vest", "say": "Attention: worker without a high visibility vest. Please wear your vest."},
        "zone": {"title": "Restricted zone entry", "say": "Warning: unauthorised entry into a restricted zone. Please step back."},
        "fall": {"title": "Fall detected", "say": "Emergency: possible fall detected. First aid team, respond immediately."},
    },
    "hi": {
        "no_helmet": {"title": "हेलमेट नहीं", "say": "ध्यान दें: एक कर्मचारी ने सुरक्षा हेलमेट नहीं पहना है। कृपया तुरंत हेलमेट पहनें।"},
        "no_vest": {"title": "सेफ्टी जैकेट नहीं", "say": "ध्यान दें: एक कर्मचारी ने सेफ्टी जैकेट नहीं पहनी है। कृपया जैकेट पहनें।"},
        "zone": {"title": "प्रतिबंधित क्षेत्र में प्रवेश", "say": "चेतावनी: प्रतिबंधित क्षेत्र में अनधिकृत प्रवेश। कृपया पीछे हटें।"},
        "fall": {"title": "गिरने की घटना", "say": "आपातकाल: किसी के गिरने की आशंका। प्राथमिक चिकित्सा टीम तुरंत पहुँचे।"},
    },
    "mr": {
        "no_helmet": {"title": "हेल्मेट नाही", "say": "लक्ष द्या: एका कामगाराने सुरक्षा हेल्मेट घातलेले नाही. कृपया लगेच हेल्मेट घाला."},
        "no_vest": {"title": "सेफ्टी जॅकेट नाही", "say": "लक्ष द्या: एका कामगाराने सेफ्टी जॅकेट घातलेले नाही. कृपया जॅकेट घाला."},
        "zone": {"title": "प्रतिबंधित क्षेत्रात प्रवेश", "say": "इशारा: प्रतिबंधित क्षेत्रात अनधिकृत प्रवेश. कृपया मागे या."},
        "fall": {"title": "पडण्याची घटना", "say": "आणीबाणी: कोणीतरी पडल्याची शक्यता. प्रथमोपचार पथकाने त्वरित यावे."},
    },
}
