# -*- coding: utf-8 -*-
"""
Códigos telefónicos de todos los países del mundo + validación de dígitos.

Estructura de cada país:
    {
        "code":    "+51",       # Código telefónico (con +)
        "name":    "Perú",      # Nombre en español
        "iso":     "PE",        # Código ISO-3166 alfa-2
        "flag":    "🇵🇪",       # Bandera emoji
        "min":     9,           # Mínimo dígitos del número (sin código)
        "max":     9,           # Máximo dígitos del número (sin código)
    }

Las primeras entradas son Latinoamérica (priorizadas para el portal CGM).
Después continúa alfabéticamente por región.
"""

PAISES_CELULAR = [
    # ── Latinoamérica y Caribe ───────────────────────────────────────────────
    {"code": "+51",  "name": "Perú",                       "iso": "PE", "flag": "🇵🇪", "min": 9,  "max": 9},
    {"code": "+54",  "name": "Argentina",                  "iso": "AR", "flag": "🇦🇷", "min": 10, "max": 10},
    {"code": "+591", "name": "Bolivia",                    "iso": "BO", "flag": "🇧🇴", "min": 8,  "max": 8},
    {"code": "+55",  "name": "Brasil",                     "iso": "BR", "flag": "🇧🇷", "min": 10, "max": 11},
    {"code": "+56",  "name": "Chile",                      "iso": "CL", "flag": "🇨🇱", "min": 9,  "max": 9},
    {"code": "+57",  "name": "Colombia",                   "iso": "CO", "flag": "🇨🇴", "min": 10, "max": 10},
    {"code": "+506", "name": "Costa Rica",                 "iso": "CR", "flag": "🇨🇷", "min": 8,  "max": 8},
    {"code": "+53",  "name": "Cuba",                       "iso": "CU", "flag": "🇨🇺", "min": 8,  "max": 8},
    {"code": "+593", "name": "Ecuador",                    "iso": "EC", "flag": "🇪🇨", "min": 9,  "max": 9},
    {"code": "+503", "name": "El Salvador",                "iso": "SV", "flag": "🇸🇻", "min": 8,  "max": 8},
    {"code": "+502", "name": "Guatemala",                  "iso": "GT", "flag": "🇬🇹", "min": 8,  "max": 8},
    {"code": "+509", "name": "Haití",                      "iso": "HT", "flag": "🇭🇹", "min": 8,  "max": 8},
    {"code": "+504", "name": "Honduras",                   "iso": "HN", "flag": "🇭🇳", "min": 8,  "max": 8},
    {"code": "+52",  "name": "México",                     "iso": "MX", "flag": "🇲🇽", "min": 10, "max": 10},
    {"code": "+505", "name": "Nicaragua",                  "iso": "NI", "flag": "🇳🇮", "min": 8,  "max": 8},
    {"code": "+507", "name": "Panamá",                     "iso": "PA", "flag": "🇵🇦", "min": 8,  "max": 8},
    {"code": "+595", "name": "Paraguay",                   "iso": "PY", "flag": "🇵🇾", "min": 9,  "max": 9},
    {"code": "+1",   "name": "Puerto Rico",                "iso": "PR", "flag": "🇵🇷", "min": 10, "max": 10},
    {"code": "+1",   "name": "República Dominicana",       "iso": "DO", "flag": "🇩🇴", "min": 10, "max": 10},
    {"code": "+598", "name": "Uruguay",                    "iso": "UY", "flag": "🇺🇾", "min": 8,  "max": 9},
    {"code": "+58",  "name": "Venezuela",                  "iso": "VE", "flag": "🇻🇪", "min": 10, "max": 10},

    # ── Norteamérica ────────────────────────────────────────────────────────
    {"code": "+1",   "name": "Canadá",                     "iso": "CA", "flag": "🇨🇦", "min": 10, "max": 10},
    {"code": "+1",   "name": "Estados Unidos",             "iso": "US", "flag": "🇺🇸", "min": 10, "max": 10},

    # ── Europa ──────────────────────────────────────────────────────────────
    {"code": "+355", "name": "Albania",                    "iso": "AL", "flag": "🇦🇱", "min": 9,  "max": 9},
    {"code": "+49",  "name": "Alemania",                   "iso": "DE", "flag": "🇩🇪", "min": 10, "max": 11},
    {"code": "+376", "name": "Andorra",                    "iso": "AD", "flag": "🇦🇩", "min": 6,  "max": 9},
    {"code": "+43",  "name": "Austria",                    "iso": "AT", "flag": "🇦🇹", "min": 10, "max": 13},
    {"code": "+32",  "name": "Bélgica",                    "iso": "BE", "flag": "🇧🇪", "min": 9,  "max": 9},
    {"code": "+375", "name": "Bielorrusia",                "iso": "BY", "flag": "🇧🇾", "min": 9,  "max": 9},
    {"code": "+387", "name": "Bosnia y Herzegovina",       "iso": "BA", "flag": "🇧🇦", "min": 8,  "max": 9},
    {"code": "+359", "name": "Bulgaria",                   "iso": "BG", "flag": "🇧🇬", "min": 9,  "max": 9},
    {"code": "+357", "name": "Chipre",                     "iso": "CY", "flag": "🇨🇾", "min": 8,  "max": 8},
    {"code": "+385", "name": "Croacia",                    "iso": "HR", "flag": "🇭🇷", "min": 8,  "max": 12},
    {"code": "+45",  "name": "Dinamarca",                  "iso": "DK", "flag": "🇩🇰", "min": 8,  "max": 8},
    {"code": "+421", "name": "Eslovaquia",                 "iso": "SK", "flag": "🇸🇰", "min": 9,  "max": 9},
    {"code": "+386", "name": "Eslovenia",                  "iso": "SI", "flag": "🇸🇮", "min": 8,  "max": 8},
    {"code": "+34",  "name": "España",                     "iso": "ES", "flag": "🇪🇸", "min": 9,  "max": 9},
    {"code": "+372", "name": "Estonia",                    "iso": "EE", "flag": "🇪🇪", "min": 7,  "max": 10},
    {"code": "+358", "name": "Finlandia",                  "iso": "FI", "flag": "🇫🇮", "min": 9,  "max": 12},
    {"code": "+33",  "name": "Francia",                    "iso": "FR", "flag": "🇫🇷", "min": 9,  "max": 9},
    {"code": "+30",  "name": "Grecia",                     "iso": "GR", "flag": "🇬🇷", "min": 10, "max": 10},
    {"code": "+36",  "name": "Hungría",                    "iso": "HU", "flag": "🇭🇺", "min": 9,  "max": 9},
    {"code": "+353", "name": "Irlanda",                    "iso": "IE", "flag": "🇮🇪", "min": 9,  "max": 9},
    {"code": "+354", "name": "Islandia",                   "iso": "IS", "flag": "🇮🇸", "min": 7,  "max": 9},
    {"code": "+39",  "name": "Italia",                     "iso": "IT", "flag": "🇮🇹", "min": 9,  "max": 11},
    {"code": "+371", "name": "Letonia",                    "iso": "LV", "flag": "🇱🇻", "min": 8,  "max": 8},
    {"code": "+423", "name": "Liechtenstein",              "iso": "LI", "flag": "🇱🇮", "min": 7,  "max": 7},
    {"code": "+370", "name": "Lituania",                   "iso": "LT", "flag": "🇱🇹", "min": 8,  "max": 8},
    {"code": "+352", "name": "Luxemburgo",                 "iso": "LU", "flag": "🇱🇺", "min": 4,  "max": 11},
    {"code": "+356", "name": "Malta",                      "iso": "MT", "flag": "🇲🇹", "min": 8,  "max": 8},
    {"code": "+373", "name": "Moldavia",                   "iso": "MD", "flag": "🇲🇩", "min": 8,  "max": 8},
    {"code": "+377", "name": "Mónaco",                     "iso": "MC", "flag": "🇲🇨", "min": 8,  "max": 8},
    {"code": "+382", "name": "Montenegro",                 "iso": "ME", "flag": "🇲🇪", "min": 7,  "max": 9},
    {"code": "+47",  "name": "Noruega",                    "iso": "NO", "flag": "🇳🇴", "min": 8,  "max": 8},
    {"code": "+31",  "name": "Países Bajos",               "iso": "NL", "flag": "🇳🇱", "min": 9,  "max": 9},
    {"code": "+48",  "name": "Polonia",                    "iso": "PL", "flag": "🇵🇱", "min": 9,  "max": 9},
    {"code": "+351", "name": "Portugal",                   "iso": "PT", "flag": "🇵🇹", "min": 9,  "max": 9},
    {"code": "+44",  "name": "Reino Unido",                "iso": "GB", "flag": "🇬🇧", "min": 10, "max": 10},
    {"code": "+420", "name": "República Checa",            "iso": "CZ", "flag": "🇨🇿", "min": 9,  "max": 9},
    {"code": "+389", "name": "Macedonia del Norte",        "iso": "MK", "flag": "🇲🇰", "min": 8,  "max": 8},
    {"code": "+40",  "name": "Rumania",                    "iso": "RO", "flag": "🇷🇴", "min": 9,  "max": 9},
    {"code": "+7",   "name": "Rusia",                      "iso": "RU", "flag": "🇷🇺", "min": 10, "max": 10},
    {"code": "+378", "name": "San Marino",                 "iso": "SM", "flag": "🇸🇲", "min": 6,  "max": 10},
    {"code": "+381", "name": "Serbia",                     "iso": "RS", "flag": "🇷🇸", "min": 8,  "max": 9},
    {"code": "+46",  "name": "Suecia",                     "iso": "SE", "flag": "🇸🇪", "min": 7,  "max": 13},
    {"code": "+41",  "name": "Suiza",                      "iso": "CH", "flag": "🇨🇭", "min": 9,  "max": 9},
    {"code": "+90",  "name": "Turquía",                    "iso": "TR", "flag": "🇹🇷", "min": 10, "max": 10},
    {"code": "+380", "name": "Ucrania",                    "iso": "UA", "flag": "🇺🇦", "min": 9,  "max": 9},
    {"code": "+379", "name": "Ciudad del Vaticano",        "iso": "VA", "flag": "🇻🇦", "min": 9,  "max": 11},

    # ── Asia ────────────────────────────────────────────────────────────────
    {"code": "+93",  "name": "Afganistán",                 "iso": "AF", "flag": "🇦🇫", "min": 9,  "max": 9},
    {"code": "+966", "name": "Arabia Saudita",             "iso": "SA", "flag": "🇸🇦", "min": 9,  "max": 9},
    {"code": "+374", "name": "Armenia",                    "iso": "AM", "flag": "🇦🇲", "min": 8,  "max": 8},
    {"code": "+994", "name": "Azerbaiyán",                 "iso": "AZ", "flag": "🇦🇿", "min": 9,  "max": 9},
    {"code": "+880", "name": "Bangladés",                  "iso": "BD", "flag": "🇧🇩", "min": 10, "max": 10},
    {"code": "+973", "name": "Baréin",                     "iso": "BH", "flag": "🇧🇭", "min": 8,  "max": 8},
    {"code": "+975", "name": "Bután",                      "iso": "BT", "flag": "🇧🇹", "min": 7,  "max": 8},
    {"code": "+673", "name": "Brunéi",                     "iso": "BN", "flag": "🇧🇳", "min": 7,  "max": 7},
    {"code": "+855", "name": "Camboya",                    "iso": "KH", "flag": "🇰🇭", "min": 8,  "max": 9},
    {"code": "+86",  "name": "China",                      "iso": "CN", "flag": "🇨🇳", "min": 11, "max": 11},
    {"code": "+850", "name": "Corea del Norte",            "iso": "KP", "flag": "🇰🇵", "min": 10, "max": 10},
    {"code": "+82",  "name": "Corea del Sur",              "iso": "KR", "flag": "🇰🇷", "min": 9,  "max": 11},
    {"code": "+971", "name": "Emiratos Árabes Unidos",     "iso": "AE", "flag": "🇦🇪", "min": 9,  "max": 9},
    {"code": "+63",  "name": "Filipinas",                  "iso": "PH", "flag": "🇵🇭", "min": 10, "max": 10},
    {"code": "+995", "name": "Georgia",                    "iso": "GE", "flag": "🇬🇪", "min": 9,  "max": 9},
    {"code": "+91",  "name": "India",                      "iso": "IN", "flag": "🇮🇳", "min": 10, "max": 10},
    {"code": "+62",  "name": "Indonesia",                  "iso": "ID", "flag": "🇮🇩", "min": 9,  "max": 12},
    {"code": "+964", "name": "Irak",                       "iso": "IQ", "flag": "🇮🇶", "min": 10, "max": 10},
    {"code": "+98",  "name": "Irán",                       "iso": "IR", "flag": "🇮🇷", "min": 10, "max": 10},
    {"code": "+972", "name": "Israel",                     "iso": "IL", "flag": "🇮🇱", "min": 9,  "max": 9},
    {"code": "+81",  "name": "Japón",                      "iso": "JP", "flag": "🇯🇵", "min": 10, "max": 10},
    {"code": "+962", "name": "Jordania",                   "iso": "JO", "flag": "🇯🇴", "min": 9,  "max": 9},
    {"code": "+7",   "name": "Kazajistán",                 "iso": "KZ", "flag": "🇰🇿", "min": 10, "max": 10},
    {"code": "+996", "name": "Kirguistán",                 "iso": "KG", "flag": "🇰🇬", "min": 9,  "max": 9},
    {"code": "+965", "name": "Kuwait",                     "iso": "KW", "flag": "🇰🇼", "min": 8,  "max": 8},
    {"code": "+856", "name": "Laos",                       "iso": "LA", "flag": "🇱🇦", "min": 8,  "max": 10},
    {"code": "+961", "name": "Líbano",                     "iso": "LB", "flag": "🇱🇧", "min": 7,  "max": 8},
    {"code": "+60",  "name": "Malasia",                    "iso": "MY", "flag": "🇲🇾", "min": 9,  "max": 10},
    {"code": "+960", "name": "Maldivas",                   "iso": "MV", "flag": "🇲🇻", "min": 7,  "max": 7},
    {"code": "+976", "name": "Mongolia",                   "iso": "MN", "flag": "🇲🇳", "min": 8,  "max": 8},
    {"code": "+95",  "name": "Myanmar",                    "iso": "MM", "flag": "🇲🇲", "min": 7,  "max": 10},
    {"code": "+977", "name": "Nepal",                      "iso": "NP", "flag": "🇳🇵", "min": 10, "max": 10},
    {"code": "+968", "name": "Omán",                       "iso": "OM", "flag": "🇴🇲", "min": 8,  "max": 8},
    {"code": "+92",  "name": "Pakistán",                   "iso": "PK", "flag": "🇵🇰", "min": 10, "max": 10},
    {"code": "+970", "name": "Palestina",                  "iso": "PS", "flag": "🇵🇸", "min": 9,  "max": 9},
    {"code": "+974", "name": "Catar",                      "iso": "QA", "flag": "🇶🇦", "min": 8,  "max": 8},
    {"code": "+65",  "name": "Singapur",                   "iso": "SG", "flag": "🇸🇬", "min": 8,  "max": 8},
    {"code": "+963", "name": "Siria",                      "iso": "SY", "flag": "🇸🇾", "min": 8,  "max": 9},
    {"code": "+94",  "name": "Sri Lanka",                  "iso": "LK", "flag": "🇱🇰", "min": 9,  "max": 9},
    {"code": "+66",  "name": "Tailandia",                  "iso": "TH", "flag": "🇹🇭", "min": 9,  "max": 9},
    {"code": "+886", "name": "Taiwán",                     "iso": "TW", "flag": "🇹🇼", "min": 9,  "max": 9},
    {"code": "+992", "name": "Tayikistán",                 "iso": "TJ", "flag": "🇹🇯", "min": 9,  "max": 9},
    {"code": "+670", "name": "Timor Oriental",             "iso": "TL", "flag": "🇹🇱", "min": 7,  "max": 8},
    {"code": "+993", "name": "Turkmenistán",               "iso": "TM", "flag": "🇹🇲", "min": 8,  "max": 8},
    {"code": "+998", "name": "Uzbekistán",                 "iso": "UZ", "flag": "🇺🇿", "min": 9,  "max": 9},
    {"code": "+84",  "name": "Vietnam",                    "iso": "VN", "flag": "🇻🇳", "min": 9,  "max": 10},
    {"code": "+967", "name": "Yemen",                      "iso": "YE", "flag": "🇾🇪", "min": 9,  "max": 9},

    # ── África ──────────────────────────────────────────────────────────────
    {"code": "+213", "name": "Argelia",                    "iso": "DZ", "flag": "🇩🇿", "min": 9,  "max": 9},
    {"code": "+244", "name": "Angola",                     "iso": "AO", "flag": "🇦🇴", "min": 9,  "max": 9},
    {"code": "+229", "name": "Benín",                      "iso": "BJ", "flag": "🇧🇯", "min": 8,  "max": 8},
    {"code": "+267", "name": "Botsuana",                   "iso": "BW", "flag": "🇧🇼", "min": 7,  "max": 8},
    {"code": "+226", "name": "Burkina Faso",               "iso": "BF", "flag": "🇧🇫", "min": 8,  "max": 8},
    {"code": "+257", "name": "Burundi",                    "iso": "BI", "flag": "🇧🇮", "min": 8,  "max": 8},
    {"code": "+238", "name": "Cabo Verde",                 "iso": "CV", "flag": "🇨🇻", "min": 7,  "max": 7},
    {"code": "+237", "name": "Camerún",                    "iso": "CM", "flag": "🇨🇲", "min": 8,  "max": 9},
    {"code": "+235", "name": "Chad",                       "iso": "TD", "flag": "🇹🇩", "min": 8,  "max": 8},
    {"code": "+269", "name": "Comoras",                    "iso": "KM", "flag": "🇰🇲", "min": 7,  "max": 7},
    {"code": "+225", "name": "Costa de Marfil",            "iso": "CI", "flag": "🇨🇮", "min": 8,  "max": 10},
    {"code": "+20",  "name": "Egipto",                     "iso": "EG", "flag": "🇪🇬", "min": 10, "max": 10},
    {"code": "+291", "name": "Eritrea",                    "iso": "ER", "flag": "🇪🇷", "min": 7,  "max": 7},
    {"code": "+251", "name": "Etiopía",                    "iso": "ET", "flag": "🇪🇹", "min": 9,  "max": 9},
    {"code": "+241", "name": "Gabón",                      "iso": "GA", "flag": "🇬🇦", "min": 7,  "max": 8},
    {"code": "+220", "name": "Gambia",                     "iso": "GM", "flag": "🇬🇲", "min": 7,  "max": 7},
    {"code": "+233", "name": "Ghana",                      "iso": "GH", "flag": "🇬🇭", "min": 9,  "max": 9},
    {"code": "+224", "name": "Guinea",                     "iso": "GN", "flag": "🇬🇳", "min": 8,  "max": 9},
    {"code": "+245", "name": "Guinea-Bisáu",               "iso": "GW", "flag": "🇬🇼", "min": 7,  "max": 7},
    {"code": "+240", "name": "Guinea Ecuatorial",          "iso": "GQ", "flag": "🇬🇶", "min": 9,  "max": 9},
    {"code": "+254", "name": "Kenia",                      "iso": "KE", "flag": "🇰🇪", "min": 9,  "max": 9},
    {"code": "+266", "name": "Lesoto",                     "iso": "LS", "flag": "🇱🇸", "min": 8,  "max": 8},
    {"code": "+231", "name": "Liberia",                    "iso": "LR", "flag": "🇱🇷", "min": 7,  "max": 8},
    {"code": "+218", "name": "Libia",                      "iso": "LY", "flag": "🇱🇾", "min": 9,  "max": 9},
    {"code": "+261", "name": "Madagascar",                 "iso": "MG", "flag": "🇲🇬", "min": 9,  "max": 9},
    {"code": "+265", "name": "Malaui",                     "iso": "MW", "flag": "🇲🇼", "min": 9,  "max": 9},
    {"code": "+223", "name": "Malí",                       "iso": "ML", "flag": "🇲🇱", "min": 8,  "max": 8},
    {"code": "+212", "name": "Marruecos",                  "iso": "MA", "flag": "🇲🇦", "min": 9,  "max": 9},
    {"code": "+230", "name": "Mauricio",                   "iso": "MU", "flag": "🇲🇺", "min": 7,  "max": 7},
    {"code": "+222", "name": "Mauritania",                 "iso": "MR", "flag": "🇲🇷", "min": 8,  "max": 8},
    {"code": "+258", "name": "Mozambique",                 "iso": "MZ", "flag": "🇲🇿", "min": 9,  "max": 9},
    {"code": "+264", "name": "Namibia",                    "iso": "NA", "flag": "🇳🇦", "min": 7,  "max": 10},
    {"code": "+227", "name": "Níger",                      "iso": "NE", "flag": "🇳🇪", "min": 8,  "max": 8},
    {"code": "+234", "name": "Nigeria",                    "iso": "NG", "flag": "🇳🇬", "min": 10, "max": 10},
    {"code": "+236", "name": "República Centroafricana",   "iso": "CF", "flag": "🇨🇫", "min": 8,  "max": 8},
    {"code": "+242", "name": "República del Congo",        "iso": "CG", "flag": "🇨🇬", "min": 9,  "max": 9},
    {"code": "+243", "name": "Rep. Dem. del Congo",        "iso": "CD", "flag": "🇨🇩", "min": 9,  "max": 9},
    {"code": "+250", "name": "Ruanda",                     "iso": "RW", "flag": "🇷🇼", "min": 9,  "max": 9},
    {"code": "+239", "name": "Santo Tomé y Príncipe",      "iso": "ST", "flag": "🇸🇹", "min": 7,  "max": 7},
    {"code": "+221", "name": "Senegal",                    "iso": "SN", "flag": "🇸🇳", "min": 9,  "max": 9},
    {"code": "+248", "name": "Seychelles",                 "iso": "SC", "flag": "🇸🇨", "min": 7,  "max": 7},
    {"code": "+232", "name": "Sierra Leona",               "iso": "SL", "flag": "🇸🇱", "min": 8,  "max": 8},
    {"code": "+252", "name": "Somalia",                    "iso": "SO", "flag": "🇸🇴", "min": 7,  "max": 8},
    {"code": "+27",  "name": "Sudáfrica",                  "iso": "ZA", "flag": "🇿🇦", "min": 9,  "max": 9},
    {"code": "+249", "name": "Sudán",                      "iso": "SD", "flag": "🇸🇩", "min": 9,  "max": 9},
    {"code": "+211", "name": "Sudán del Sur",              "iso": "SS", "flag": "🇸🇸", "min": 9,  "max": 9},
    {"code": "+268", "name": "Esuatini",                   "iso": "SZ", "flag": "🇸🇿", "min": 8,  "max": 8},
    {"code": "+255", "name": "Tanzania",                   "iso": "TZ", "flag": "🇹🇿", "min": 9,  "max": 9},
    {"code": "+228", "name": "Togo",                       "iso": "TG", "flag": "🇹🇬", "min": 8,  "max": 8},
    {"code": "+216", "name": "Túnez",                      "iso": "TN", "flag": "🇹🇳", "min": 8,  "max": 8},
    {"code": "+256", "name": "Uganda",                     "iso": "UG", "flag": "🇺🇬", "min": 9,  "max": 9},
    {"code": "+253", "name": "Yibuti",                     "iso": "DJ", "flag": "🇩🇯", "min": 8,  "max": 8},
    {"code": "+260", "name": "Zambia",                     "iso": "ZM", "flag": "🇿🇲", "min": 9,  "max": 9},
    {"code": "+263", "name": "Zimbabue",                   "iso": "ZW", "flag": "🇿🇼", "min": 9,  "max": 10},

    # ── Oceanía ─────────────────────────────────────────────────────────────
    {"code": "+61",  "name": "Australia",                  "iso": "AU", "flag": "🇦🇺", "min": 9,  "max": 9},
    {"code": "+679", "name": "Fiyi",                       "iso": "FJ", "flag": "🇫🇯", "min": 7,  "max": 7},
    {"code": "+686", "name": "Kiribati",                   "iso": "KI", "flag": "🇰🇮", "min": 5,  "max": 8},
    {"code": "+692", "name": "Islas Marshall",             "iso": "MH", "flag": "🇲🇭", "min": 7,  "max": 7},
    {"code": "+691", "name": "Micronesia",                 "iso": "FM", "flag": "🇫🇲", "min": 7,  "max": 7},
    {"code": "+674", "name": "Nauru",                      "iso": "NR", "flag": "🇳🇷", "min": 7,  "max": 7},
    {"code": "+64",  "name": "Nueva Zelanda",              "iso": "NZ", "flag": "🇳🇿", "min": 8,  "max": 10},
    {"code": "+680", "name": "Palaos",                     "iso": "PW", "flag": "🇵🇼", "min": 7,  "max": 7},
    {"code": "+675", "name": "Papúa Nueva Guinea",         "iso": "PG", "flag": "🇵🇬", "min": 7,  "max": 8},
    {"code": "+677", "name": "Islas Salomón",              "iso": "SB", "flag": "🇸🇧", "min": 5,  "max": 7},
    {"code": "+685", "name": "Samoa",                      "iso": "WS", "flag": "🇼🇸", "min": 5,  "max": 7},
    {"code": "+676", "name": "Tonga",                      "iso": "TO", "flag": "🇹🇴", "min": 5,  "max": 7},
    {"code": "+688", "name": "Tuvalu",                     "iso": "TV", "flag": "🇹🇻", "min": 5,  "max": 5},
    {"code": "+678", "name": "Vanuatu",                    "iso": "VU", "flag": "🇻🇺", "min": 5,  "max": 7},
]


# Diccionario lookup ISO → datos del país (rápido para backend)
PAISES_POR_ISO = {p["iso"]: p for p in PAISES_CELULAR}


def validar_celular(iso, digits_str):
    """Valida que `digits_str` matchee el rango de dígitos del país `iso`.
    Devuelve None si OK, o un mensaje de error."""
    pais = PAISES_POR_ISO.get((iso or "").upper())
    if not pais:
        return "Código de país no válido."
    n = len(digits_str)
    if n < pais["min"] or n > pais["max"]:
        if pais["min"] == pais["max"]:
            return f"El celular para {pais['name']} debe tener exactamente {pais['min']} dígitos."
        return f"El celular para {pais['name']} debe tener entre {pais['min']} y {pais['max']} dígitos."
    return None


def codigo_default(portal):
    """Devuelve el ISO del país default según el portal (PE/AR)."""
    return "PE" if (portal or "").lower() != "ar" else "AR"
