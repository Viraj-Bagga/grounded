"""PRIORITY 3: register breadth, 2026-09-19. Same presentations, other voices.

Two rules shaped what got multiplied:

1. NOT the single-colour clusters. Another panic green or another pleurisy
   yellow deepens exactly the chunk-to-colour shortcut the set exists to break,
   so panic gets three greens and pleurisy none.
2. Weighted to green. Priorities 1 and 2 are mostly red and yellow, because most
   appended chunks are red and every contrast set carries a red or a yellow half.
   Left alone, the 80 new pairs would have trained more of the red bias the
   adapter has to remove.

The nine sets here are existing axes in new registers, plus three reflux alarm
axes: vomit like coffee grounds, trouble swallowing, and unexplained weight
loss. Each is a line in CP-GERD-002, with CP-GERD-001's "see a doctor" line, and
each gives CP-GERD a yellow against a green on the same chunks.
"""


def prof(age, sex, conditions=(), medications=()):
    return (f"age: {age}, sex: {sex}\n"
            f"conditions: {', '.join(conditions) or 'none'}\n"
            f"medications: {', '.join(medications) or 'none'}")


VTE_AXIS = ("Deep vein thrombosis (DVT) should be taken seriously, as it may lead to a life-threatening "
            "pulmonary embolism (PE).")
VTE_LEG = ("Swollen and tender legs that are painful to the touch, if you have blood clots that block "
           "blood flow to your leg veins ( deep vein thrombosis or DVT )")
VTE_LUNG = ("Shortness of breath and pain when breathing, if you have a blood clot that travels to the "
            "lungs ( pulmonary embolism )")
VTE_CALL = "Call your healthcare provider right away if you think you may have symptoms of VTE."
PE_HISTORY = "Blood clotting disorders or a history of blood clots"
PE_OBESITY = "Obesity, which can lead to inflammation and damage in the lining of blood vessels"
PE_KIDNEY = "Kidney disease , which makes the blood clot more easily"
DIFF_IMMEDIATE = ("Get immediate medical care if you have chest pain that does not go away, crushing pain "
                  "or pressure in the chest, or chest pain along with nausea, sweating, dizziness or "
                  "shortness of breath.")
DIFF_NOTALWAYS = "It does not always mean that you are having a heart attack ."
DIFF_MUSCLES = "Sore muscles"
PNA1_LIST = ["Chest pain when you breathe or cough", "Cough with or without mucus", "Fever", "Chills"]
PNA1_SOB = "Shortness of breath"
PNA1_RISK = ("Young children, older adults, and people who have serious health conditions are at risk for "
             "developing more serious pneumonia or life-threatening complications.")
PNA1_CONFUSED = "Older adults who have pneumonia may feel weak or suddenly confused."
PNA2_OTHER = ("Other serious conditions, such as malnutrition, diabetes , heart failure , sickle cell "
              "disease , or liver or kidney disease, are additional risk factors.")
ANG5_EXERTION = "Pain that occurs during physical activity or mental stress"
ANG5_REST = "Pain that is relieved by rest or medicines"
ANG5_5MIN = "Symptoms that go away within 5 minutes"
ANG6_REST = "Pain during rest or sleep"
ANG9_STABLE = ("If you have stable angina, you can learn its pattern and predict when an event will "
               "occur, such as during physical activity or mental stress.")
ANG10_EMERGENCY = "Unstable angina is a medical emergency because it can progress to a heart attack ."
PERI_CALL = ("If you have chest pain or severe shortness of breath, or your symptoms get worse, call "
             "9-1-1 or seek medical help right away.")
PERI_VIRUS = ("If a virus causes your heart inflammation, you may have a cough, runny nose, or "
              "gastrointestinal symptoms a few weeks before you notice any other symptoms of heart "
              "inflammation.")
PERI_PAIN = ("Chest pain that feels sharp, gets worse with breathing, and feels better with sitting up and "
             "leaning forward")
GERD_HEARTBURN = ("heartburn , a painful, burning feeling in the middle of your chest, behind your "
                  "breastbone, rising from the lower tip of your breastbone toward your throat")
GERD_REGURG = ("regurgitation, or stomach contents coming back up through your esophagus and into your "
               "throat or mouth, which may cause you to taste food or stomach acid")
GERD_SEEDOC = ("You should see a doctor if you think you have GERD, or if your symptoms don’t get better "
               "with over-the-counter medicines or lifestyle changes.")
GERD_COMPLICATIONS = ("You should also see a doctor if you have symptoms that could be related to GERD "
                      "complications or other serious health problems, such as")
GERD_COFFEE = "vomit that contains blood or looks like coffee grounds"
GERD_SWALLOW = "problems swallowing or pain while swallowing"
GERD_WEIGHT = "unexplained weight loss"
GERD_TARRY = "stool that contains blood or looks black and tarry"
PANIC_PHYSICAL = ["Pounding or racing heart", "Trembling", "Tingly or numb hands",
                  "A feeling of being out of control"]
PANIC_NOTFATAL = ("While these feelings can be distressing, panic attacks themselves are not "
                  "life-threatening, and the physical symptoms usually resolve with time.")
PANIC_LIKEHEART = ("Panic attacks often include physical symptoms that might feel like a heart attack, "
                   "such as trembling or tingling in the body or a rapid heart rate.")
PANIC_ANYTIME = "Panic attacks can occur at any time, sometimes even during sleep."
ACS3_LIST = ["Chest pain, heaviness, or discomfort in the center or left side of the chest (this is the "
             "most common symptom)",
             "Pain or discomfort in one or both arms, your back, shoulders, neck, jaw, or above your "
             "belly button", "Sweating a lot for no reason", "Nausea (feeling sick to the stomach) and "
             "vomiting"]
ACS5_NOTGOAWAY = ("The pain from a heart attack is more serious than the pain from angina. Heart attack "
                  "pain doesn’t go away when you rest or take medicine.")
ACS5_CALL = "If you don’t know whether your chest pain is angina or a heart attack, call 9-1-1."

PAIRS = {}


def add(pid, slot, profile, symptoms, answer, timeline=None):
    PAIRS[pid] = {"slot": slot, "profile": profile, "symptoms": symptoms, "answer": answer,
                  **({"timeline": timeline} if timeline else {})}


def cset(cid, axis, keys, register, quotes, axis_quote):
    def slot(cat, side):
        return {"kind": "contrast", "target_category": cat, "reference_keys": list(keys),
                "register": register, "contrast_id": cid, "contrast_axis": axis,
                "contrast_side": side, "axis_quote": axis_quote, "quotes": quotes}
    return slot


def one(cat, keys, register, quotes, kind="standalone", note=None):
    s = {"kind": kind, "target_category": cat, "reference_keys": list(keys), "register": register,
         "quotes": quotes}
    if note:
        s["grounding_note"] = note
    return s


# ===========================================================================
# NINE CONTRAST SETS
# ===========================================================================
_c21 = cset("C21", "have breathing symptoms joined the swollen leg", ["CP-PE-001", "CP-PE-004"],
            "poor spelling and punctuation",
            {"CP-PE-001": [VTE_AXIS, VTE_LEG, VTE_LUNG, VTE_CALL], "CP-PE-004": [PE_HISTORY]},
            {"CP-PE-001": VTE_AXIS})
add("P0096", _c21("yellow", "swollen tender calf with a past clot, breathing normal"),
    prof(50, "male", ["previous deep vein thrombosis"]),
    "had a clot in my leg 2 yrs ago. same leg swollen again since sunday n the calf is sore when i press "
    "it. breathin is fine n no chest pain",
    {"urgency": "yellow",
     "rationale": "One-sided leg swelling with a tender calf in a man who has had a clot before. The "
                  "retrieved context lists swollen, tender legs as the sign of a clot in the leg veins, "
                  "names a history of blood clots as a risk factor, and says to call a healthcare "
                  "provider right away. No breathing symptoms.",
     "red_flags": ["Same leg swollen again for days, calf sore to press"],
     "next_steps": ["Get the leg assessed today and say you have had a clot before",
                    "Call emergency services if you become short of breath or it hurts to breathe in"],
     "citations": ["CP-PE-001", "CP-PE-004"], "follow_up_questions": ["Is only the one leg swollen?"]})
add("P0097", _c21("red", "swollen tender calf with a past clot, now breathless with pain on breathing in"),
    prof(50, "male", ["previous deep vein thrombosis"]),
    "had a clot in my leg 2 yrs ago. same leg swollen again since sunday n the calf is sore when i press "
    "it. since lunch im short of breath n it hurts when i breathe in",
    {"urgency": "red",
     "rationale": "One-sided leg swelling in a man with a previous clot, now with breathlessness and pain "
                  "on breathing in since lunchtime. The retrieved context names those two as the signs of "
                  "a clot that has travelled to the lungs and calls pulmonary embolism life-threatening.",
     "red_flags": ["Short of breath since lunchtime, with a swollen tender calf",
                   "Pain on breathing in, new today"],
     "next_steps": ["Call emergency services now", "Do not drive yourself"],
     "citations": ["CP-PE-001", "CP-PE-004"], "follow_up_questions": []})

_c22 = cset("C22", "is there breathlessness alongside the chest pain", ["CP-PNA-001", "CP-DIFF-001"],
            "poor spelling and punctuation",
            {"CP-PNA-001": PNA1_LIST + [PNA1_SOB], "CP-DIFF-001": [DIFF_IMMEDIATE]},
            {"CP-DIFF-001": DIFF_IMMEDIATE})
add("P0098", _c22("yellow", "five days of fever and productive cough with chest pain on coughing, breathing fine"),
    prof(39, "female"),
    "fever n coughin up phlegm 5 days now, chest hurts when i cough. breathin is ok",
    {"urgency": "yellow",
     "rationale": "Five days of fever with a productive cough and chest pain on coughing, which the "
                  "retrieved context lists among the symptoms of pneumonia. Breathing is unaffected, so "
                  "none of the features the context sends for immediate care are present.",
     "red_flags": ["Chest pain on coughing, after five days of fever"],
     "next_steps": ["Be seen by your GP today",
                    "Call emergency services if you become short of breath at rest"],
     "citations": ["CP-PNA-001", "CP-DIFF-001"],
     "follow_up_questions": ["What colour is the phlegm?"]})
add("P0099", _c22("red", "five days of fever and productive cough with chest pain on coughing, now short of breath at rest"),
    prof(39, "female"),
    "fever n coughin up phlegm 5 days now, chest hurts when i cough. now im short of breath just sittin "
    "here",
    {"urgency": "red",
     "rationale": "Five days of fever with a productive cough and chest pain on coughing, now with "
                  "breathlessness at rest. The retrieved context says chest pain along with shortness of "
                  "breath needs immediate medical care.",
     "red_flags": ["Short of breath at rest", "Chest pain on coughing, after five days of fever"],
     "next_steps": ["Call emergency services now", "Sit upright while you wait"],
     "citations": ["CP-PNA-001", "CP-DIFF-001"], "follow_up_questions": []})

_c23 = cset("C23", "has an older adult become suddenly confused", ["CP-PNA-001"], "plain and factual",
            {"CP-PNA-001": PNA1_LIST + [PNA1_RISK, PNA1_CONFUSED]}, {"CP-PNA-001": PNA1_CONFUSED})
add("P0100", _c23("yellow", "two days of cough and fever with chest pain on coughing, alert and oriented"),
    prof(86, "male", ["atrial fibrillation"], ["apixaban"]),
    "My grandfather has had a cough with a fever for two days and his chest hurts when he coughs. He is "
    "alert, eating, and his breathing is normal.",
    {"urgency": "yellow",
     "rationale": "Two days of cough and fever with chest pain on coughing in an 86-year-old. The "
                  "retrieved context lists those symptoms for pneumonia and names older adults as at risk "
                  "of more serious pneumonia. He is alert and breathing normally, so assessment today.",
     "red_flags": ["Chest pain on coughing, after two days of fever"],
     "next_steps": ["Arrange a GP visit or urgent care assessment today",
                    "Call emergency services if he becomes confused, drowsy or short of breath"],
     "citations": ["CP-PNA-001"],
     "follow_up_questions": ["Is he drinking normally?"]})
add("P0101", _c23("red", "two days of cough and fever with chest pain on coughing, now suddenly confused"),
    prof(86, "male", ["atrial fibrillation"], ["apixaban"]),
    "My grandfather has had a cough with a fever for two days and his chest hurts when he coughs. Since "
    "this afternoon he is confused and not making sense, which is not like him. His breathing is normal.",
    {"urgency": "red",
     "rationale": "Two days of cough and fever with chest pain on coughing in an 86-year-old who has "
                  "become confused this afternoon. The retrieved context says older adults with pneumonia "
                  "may become suddenly confused and that older adults are at risk of life-threatening "
                  "complications.",
     "red_flags": ["Confused since this afternoon, after two days of fever and cough"],
     "next_steps": ["Call emergency services now", "Stay with him until help arrives"],
     "citations": ["CP-PNA-001"], "follow_up_questions": []})

_c24 = cset("C24", "did the episode come on at rest or on exertion",
            ["CP-ANG-005", "CP-ANG-006", "CP-ANG-010"], "terse adult",
            {"CP-ANG-005": [ANG5_EXERTION, ANG5_REST], "CP-ANG-006": [ANG6_REST],
             "CP-ANG-010": [ANG10_EMERGENCY]}, {"CP-ANG-006": ANG6_REST})
add("P0102", _c24("yellow", "known angina on exertion, settled in four minutes"),
    prof(72, "male", ["coronary artery disease"], ["aspirin", "ramipril"]),
    "Known angina. Chest went tight mowing the lawn. Stopped. Gone in four minutes.",
    {"urgency": "yellow",
     "rationale": "Known angina brought on by exertion and relieved within four minutes of stopping, "
                  "which is the stable pattern in the retrieved context. None of the unstable features "
                  "are present.",
     "red_flags": ["Chest tightness on exertion in known coronary artery disease"],
     "next_steps": ["Arrange a GP or heart team review today",
                    "Call emergency services if one starts at rest or does not settle when you stop"],
     "citations": ["CP-ANG-005", "CP-ANG-006"],
     "follow_up_questions": ["Coming on with less effort than before?"]})
add("P0103", _c24("red", "known angina at rest, settled in four minutes"),
    prof(72, "male", ["coronary artery disease"], ["aspirin", "ramipril"]),
    "Known angina. Chest went tight sitting watching television, doing nothing. Gone in four minutes.",
    {"urgency": "red",
     "rationale": "The same angina tightness, but it came on at rest rather than on exertion. The "
                  "retrieved context lists pain during rest among the unstable features and says unstable "
                  "angina is a medical emergency. A short episode does not change that.",
     "red_flags": ["Angina tightness at rest, with no exertion"],
     "next_steps": ["Call emergency services now", "Do not drive yourself"],
     "citations": ["CP-ANG-006", "CP-ANG-010"], "follow_up_questions": []})

_c25 = cset("C25", "is there breathlessness at rest", ["CP-PERI-001", "CP-PERI-002"],
            "panicked caregiver", {"CP-PERI-001": [PERI_CALL, PERI_VIRUS], "CP-PERI-002": [PERI_PAIN]},
            {"CP-PERI-001": PERI_CALL})
add("P0104", _c25("yellow", "positional pleuritic pain after a cold, breathing comfortably"),
    prof(31, "male"),
    "My boyfriend has had a sharp pain in his chest for two days, ever since a cold! It is worse when he "
    "breathes in and better when he leans forward! He is breathing fine otherwise!",
    {"urgency": "yellow",
     "rationale": "Two days of sharp chest pain that is worse on breathing in and better leaning forward, "
                  "after a cold. The retrieved context describes that pattern and says a virus can precede "
                  "it. He is not severely breathless and not getting worse, so this is the seek-help-right-"
                  "away branch rather than 9-1-1.",
     "red_flags": ["Sharp chest pain worse on breathing in, eased leaning forward"],
     "next_steps": ["Get him assessed today", "Call emergency services if he becomes breathless at rest "
                    "or the pain gets worse"],
     "citations": ["CP-PERI-001", "CP-PERI-002"],
     "follow_up_questions": ["Has he had a temperature with it?"]})
add("P0105", _c25("red", "positional pleuritic pain after a cold, now breathless at rest"),
    prof(31, "male"),
    "My boyfriend has had a sharp pain in his chest for two days, ever since a cold! It is worse when he "
    "breathes in and better when he leans forward, and now he is really struggling to breathe even "
    "sitting still!",
    {"urgency": "red",
     "rationale": "The same positional chest pain after a cold, now with severe breathlessness at rest. "
                  "The retrieved context says to call 9-1-1 for chest pain with severe shortness of breath "
                  "or symptoms that are getting worse.",
     "red_flags": ["Struggling to breathe at rest, new tonight",
                   "Sharp chest pain worse on breathing in, two days"],
     "next_steps": ["Call emergency services now", "Keep him sitting upright and stay with him"],
     "citations": ["CP-PERI-001", "CP-PERI-002"], "follow_up_questions": []})

_c26 = cset("C26", "is there vomit that looks like coffee grounds", ["CP-GERD-001", "CP-GERD-002"],
            "verbose and anxious",
            {"CP-GERD-001": [GERD_HEARTBURN, GERD_SEEDOC, GERD_COMPLICATIONS],
             "CP-GERD-002": [GERD_COFFEE, GERD_SWALLOW]}, {"CP-GERD-002": GERD_COFFEE})
add("P0106", _c26("green", "reflux after meals, worse lying flat, nothing else changed"),
    prof(46, "female", (), ["naproxen"]),
    "I have had heartburn after meals for a few weeks, worse if I lie down straight after eating, and it "
    "eases when I sit up. I take naproxen for my knee. Otherwise I feel completely well and nothing else "
    "has changed.",
    {"urgency": "green",
     "rationale": "A few weeks of heartburn after meals, worse lying flat and eased by sitting up, which "
                  "the retrieved context describes as typical reflux. None of the complication signs it "
                  "lists are present. Anti-inflammatory tablets can aggravate reflux, which is worth "
                  "raising with her GP in the ordinary way.",
     "red_flags": [],
     "next_steps": ["Leave two to three hours between eating and lying down",
                    "Mention the anti-inflammatory tablets to your GP at a routine appointment",
                    "Seek assessment the same day if you vomit blood or anything like coffee grounds, or "
                    "your stool turns black"],
     "citations": ["CP-GERD-001", "CP-GERD-002"], "follow_up_questions": []})
add("P0107", _c26("yellow", "reflux after meals, worse lying flat, plus vomit like coffee grounds"),
    prof(46, "female", (), ["naproxen"]),
    "I have had heartburn after meals for a few weeks, worse if I lie down straight after eating, and it "
    "eases when I sit up. I take naproxen for my knee. This morning I vomited and it looked like coffee "
    "grounds, which terrified me.",
    {"urgency": "yellow",
     "rationale": "The same reflux pattern, but she has vomited material that looks like coffee grounds. "
                  "The retrieved context lists that as a sign of bleeding in the digestive tract and says "
                  "to see a doctor for it. Anti-inflammatory tablets are named as something that "
                  "aggravates reflux.",
     "red_flags": ["Vomited material like coffee grounds, new this morning"],
     "next_steps": ["Be seen today, through your GP or an urgent care service",
                    "Go to an emergency department if you vomit blood again, feel faint or your stool "
                    "turns black"],
     "citations": ["CP-GERD-001", "CP-GERD-002"],
     "follow_up_questions": ["Have you felt faint or light-headed since it happened?"]})

_c27 = cset("C27", "is swallowing affected", ["CP-GERD-001", "CP-GERD-002"], "plain and factual",
            {"CP-GERD-001": [GERD_HEARTBURN, GERD_COMPLICATIONS], "CP-GERD-002": [GERD_SWALLOW, GERD_WEIGHT]},
            {"CP-GERD-002": GERD_SWALLOW})
add("P0108", _c27("green", "long-standing reflux, swallowing normal"),
    prof(58, "male", ["acid reflux"]),
    "I have had reflux for years. Burning behind the breastbone after big meals, eased by sitting up. "
    "Swallowing is normal and my weight is steady.",
    {"urgency": "green",
     "rationale": "Long-standing reflux with the typical burning the retrieved context describes, and none "
                  "of the complication signs it lists: swallowing is normal and weight is steady.",
     "red_flags": [],
     "next_steps": ["Keep meals smaller and avoid lying down soon after eating",
                    "Seek assessment if food starts to stick, swallowing becomes painful, or you lose "
                    "weight without trying"],
     "citations": ["CP-GERD-001", "CP-GERD-002"], "follow_up_questions": []})
add("P0109", _c27("yellow", "long-standing reflux, now trouble swallowing"),
    prof(58, "male", ["acid reflux"]),
    "I have had reflux for years. Burning behind the breastbone after big meals, eased by sitting up. "
    "Over the last month I have had trouble swallowing, food feels like it catches, and my weight is "
    "steady.",
    {"urgency": "yellow",
     "rationale": "The same long-standing reflux, but with a month of trouble swallowing. The retrieved "
                  "context lists problems swallowing among the symptoms that could be related to "
                  "complications and says to see a doctor for them.",
     "red_flags": ["Trouble swallowing food, new over recent weeks"],
     "next_steps": ["Contact your GP today and say swallowing has changed",
                    "Seek assessment sooner if you cannot swallow liquids or you vomit blood"],
     "citations": ["CP-GERD-001", "CP-GERD-002"],
     "follow_up_questions": ["Does it catch with solids, liquids, or both?"]})

_c28 = cset("C28", "is there unexplained weight loss", ["CP-GERD-001", "CP-GERD-002"], "terse adult",
            {"CP-GERD-001": [GERD_HEARTBURN, GERD_COMPLICATIONS], "CP-GERD-002": [GERD_WEIGHT, GERD_TARRY]},
            {"CP-GERD-002": GERD_WEIGHT})
add("P0110", _c28("green", "reflux most evenings, weight steady"),
    prof(52, "male"),
    "Heartburn most evenings after food. Sitting up helps. Weight steady, eating normally.",
    {"urgency": "green",
     "rationale": "Evening heartburn after food, relieved by sitting up, with a steady weight and normal "
                  "eating. That is the typical reflux the retrieved context describes, with none of the "
                  "complication signs it lists.",
     "red_flags": [],
     "next_steps": ["Try smaller evening meals and a longer gap before bed",
                    "Seek assessment if you lose weight without trying or swallowing changes"],
     "citations": ["CP-GERD-001", "CP-GERD-002"], "follow_up_questions": []})
add("P0111", _c28("yellow", "reflux most evenings, plus unexplained weight loss"),
    prof(52, "male"),
    "Heartburn most evenings after food. Sitting up helps. Lost weight over two months without trying, "
    "about a stone.",
    {"urgency": "yellow",
     "rationale": "The same evening reflux, but with unexplained weight loss over two months. The "
                  "retrieved context lists unexplained weight loss among the symptoms that could be "
                  "related to complications or other serious problems and says to see a doctor.",
     "red_flags": ["About a stone lost over eight weeks, without trying"],
     "next_steps": ["Contact your GP today and ask for an appointment about the weight loss",
                    "Seek assessment sooner if your stool turns black or you vomit blood"],
     "citations": ["CP-GERD-001", "CP-GERD-002"],
     "follow_up_questions": ["Any change in appetite or in swallowing?"]})

_c29 = cset("C29", "is the burning brought on by meals or by exertion",
            ["CP-GERD-001", "CP-ANG-003", "CP-ANG-005"], "poor spelling and punctuation",
            {"CP-GERD-001": [GERD_HEARTBURN], "CP-ANG-003": ["Heartburn or indigestion"],
             "CP-ANG-005": [ANG5_EXERTION, ANG5_REST]}, {"CP-ANG-005": ANG5_EXERTION})
add("P0112", _c29("green", "indigestion-like burning after big dinners, worse lying down"),
    prof(52, "male"),
    "past 3 months iv had a burnin feelin behind my breastbone like indigestion. comes on after big "
    "dinners wen i lie down n goes wen i sit up",
    {"urgency": "green",
     "rationale": "Three months of burning behind the breastbone after large meals, worse lying down and "
                  "eased sitting up. The retrieved context describes that as heartburn from reflux, and it "
                  "is not brought on by exertion or relieved by rest, which is the angina pattern the same "
                  "context gives.",
     "red_flags": [],
     "next_steps": ["Smaller evening meals, and leave a few hours before lying down",
                    "Seek assessment today if it starts coming on when you walk or exert yourself"],
     "citations": ["CP-GERD-001", "CP-ANG-005"], "follow_up_questions": []})
add("P0113", _c29("yellow", "indigestion-like burning brought on by walking uphill"),
    prof(52, "male"),
    "past 3 months iv had a burnin feelin behind my breastbone like indigestion. comes on wen i walk up "
    "the hill to work n goes wen i stop for a bit",
    {"urgency": "yellow",
     "rationale": "The same indigestion-like burning, but brought on by walking uphill and relieved by "
                  "stopping. The retrieved context says angina can feel like heartburn or indigestion and "
                  "gives pain on exertion relieved by rest as the angina pattern. Never assessed.",
     "red_flags": ["Burning behind the breastbone on walking uphill, eased by stopping"],
     "next_steps": ["Ask your GP to see you today", "Call emergency services if it comes on at rest or "
                    "does not ease when you stop"],
     "citations": ["CP-ANG-003", "CP-ANG-005"],
     "follow_up_questions": ["Does it spread anywhere, like your arm or jaw?"]})

# ===========================================================================
# REGISTER VARIANTS, weighted to green
# ===========================================================================
GERD_GREEN_Q = {"CP-GERD-001": [GERD_HEARTBURN, GERD_REGURG], "CP-GERD-002": [GERD_SWALLOW, GERD_WEIGHT]}
add("P0114", one("green", ["CP-GERD-001", "CP-GERD-002"], "verbose and anxious", GERD_GREEN_Q),
    prof(31, "female"),
    "Sorry if this is a silly thing to ask. After my takeaway last night I got a burning feeling rising "
    "up behind my breastbone into my throat, and a sour taste in my mouth. It has happened a few times "
    "after big meals. It went after about an hour and today I feel completely fine.",
    {"urgency": "green",
     "rationale": "Burning rising behind the breastbone into the throat with a sour taste, after a large "
                  "meal, settling within the hour and gone today. The retrieved context describes both "
                  "heartburn and regurgitation in those words, and none of the complication signs it "
                  "lists are present.",
     "red_flags": [],
     "next_steps": ["Eat earlier in the evening and keep portions smaller",
                    "Seek assessment if swallowing becomes difficult or you lose weight without trying"],
     "citations": ["CP-GERD-001", "CP-GERD-002"], "follow_up_questions": []})
add("P0115", one("green", ["CP-GERD-001", "CP-GERD-002"], "describing a third person", GERD_GREEN_Q),
    prof(44, "male"),
    "My husband gets heartburn most nights after dinner, worse when he lies on the sofa. It goes if he "
    "sits up. He is eating well and has not lost weight.",
    {"urgency": "green",
     "rationale": "Nightly heartburn after dinner, worse lying down and relieved by sitting up, with "
                  "normal eating and steady weight. The retrieved context calls that typical reflux, and "
                  "none of the complication signs it lists are present.",
     "red_flags": [],
     "next_steps": ["Leave a few hours between dinner and lying down",
                    "Raise the head of the bed if the night-time burning continues",
                    "Seek assessment if he starts to struggle swallowing or loses weight"],
     "citations": ["CP-GERD-001", "CP-GERD-002"], "follow_up_questions": []})
add("P0116", one("green", ["CP-GERD-001"], "poor spelling and punctuation",
                 {"CP-GERD-001": [GERD_HEARTBURN, GERD_REGURG, GERD_SEEDOC]}),
    prof(27, "male"),
    "heartburn n burpin after pizza n beer, burns up into my throat n taste acid. had it b4. otherwise "
    "fine",
    {"urgency": "green",
     "rationale": "Burning up into the throat with an acid taste after a heavy meal and alcohol, in "
                  "someone otherwise well and used to it. The retrieved context describes that as "
                  "heartburn with regurgitation and says to see a doctor if it does not settle with "
                  "lifestyle changes.",
     "red_flags": [],
     "next_steps": ["Smaller meals, and less alcohol with food, then see whether the pattern changes",
                    "See your GP in the ordinary way if it keeps happening",
                    "Seek assessment if swallowing gets difficult or your stool turns black"],
     "citations": ["CP-GERD-001"], "follow_up_questions": []})
add("P0117", one("green", ["CP-GERD-001", "CP-GERD-002"], "minimising the symptom", GERD_GREEN_Q),
    prof(39, "female"),
    "It is only a bit of indigestion really. It comes on if I eat late and it goes when I sit up. Nothing "
    "else wrong with me.",
    {"urgency": "green",
     "rationale": "Indigestion-type burning brought on by late eating and relieved by sitting up, with no "
                  "other symptoms. That is the reflux pattern in the retrieved context, and none of the "
                  "complication signs it lists are present. Minimising it does not change the assessment "
                  "here; the pattern itself is reassuring.",
     "red_flags": [],
     "next_steps": ["Try eating earlier in the evening",
                    "Seek assessment if it stops responding to that, or swallowing changes"],
     "citations": ["CP-GERD-001", "CP-GERD-002"], "follow_up_questions": []})
add("P0118", one("green", ["CP-GERD-001", "CP-GERD-002"], "panicked caregiver", GERD_GREEN_Q),
    prof(48, "female"),
    "My wife keeps getting burning in her chest after big meals and a sour taste at night! She says it is "
    "nothing but I am worried about her heart! She is well otherwise, eating normally, no weight loss!",
    {"urgency": "green",
     "rationale": "Burning in the chest after large meals with a sour taste at night, otherwise well. The "
                  "retrieved context describes heartburn and regurgitation in those terms. It is tied to "
                  "meals rather than exertion, and none of the complication signs listed are present.",
     "red_flags": [],
     "next_steps": ["Smaller evening meals and a longer gap before bed",
                    "Seek assessment the same day if the burning starts coming on when she exerts herself, "
                    "or she vomits blood"],
     "citations": ["CP-GERD-001", "CP-GERD-002"], "follow_up_questions": []})
add("P0119", one("green", ["CP-GERD-001", "CP-GERD-002"], "plain and factual", GERD_GREEN_Q),
    prof(33, "male"),
    "Burning behind the breastbone twice this week after late meals, worse lying flat, eases sitting up. "
    "No trouble swallowing and my weight is the same.",
    {"urgency": "green",
     "rationale": "Twice-weekly burning behind the breastbone after late meals, positional and eased by "
                  "sitting up, with normal swallowing and a steady weight. The retrieved context describes "
                  "that as reflux and lists none of its complication signs here.",
     "red_flags": [],
     "next_steps": ["Eat earlier and keep the evening meal lighter",
                    "Seek assessment if it becomes daily, swallowing changes, or you lose weight"],
     "citations": ["CP-GERD-001", "CP-GERD-002"], "follow_up_questions": []})
add("P0120", one("green", ["CP-GERD-001", "CP-GERD-002"], "terse adult", GERD_GREEN_Q),
    prof(55, "female", ["acid reflux"]),
    "Reflux after meals for years. Same as always. No swallowing trouble, no weight loss.",
    {"urgency": "green",
     "rationale": "Long-standing reflux behaving as it always has, with none of the complication signs "
                  "the retrieved context lists.",
     "red_flags": [],
     "next_steps": ["Carry on with what already helps, and keep meals earlier in the evening",
                    "Seek assessment if the pattern changes, swallowing becomes difficult, or your stool "
                    "turns black"],
     "citations": ["CP-GERD-001", "CP-GERD-002"], "follow_up_questions": []})

PANIC_Q = {"CP-PANIC-002": PANIC_PHYSICAL + [PANIC_NOTFATAL], "CP-PANIC-001": [PANIC_LIKEHEART]}
add("P0121", one("green", ["CP-PANIC-002", "CP-PANIC-001"], "terse adult", PANIC_Q),
    prof(24, "male", ["panic disorder"], ["sertraline"]),
    "On the tube. Heart hammering, hands tingling, felt unreal and out of control. Got off, passed in ten "
    "minutes. Had dozens of these.",
    {"urgency": "green",
     "rationale": "A racing heart with tingling hands and a feeling of being out of control, lasting ten "
                  "minutes and settling, in a man with diagnosed panic disorder who recognises it. The "
                  "retrieved context lists those physical symptoms for a panic attack, notes they can feel "
                  "like a heart attack, and says panic attacks themselves are not life-threatening and the "
                  "symptoms usually resolve with time.",
     "red_flags": [],
     "next_steps": ["Sit somewhere quiet and let it settle, as you already did",
                    "Seek care the same day if an attack feels different from your usual ones or does not "
                    "settle"],
     "citations": ["CP-PANIC-002", "CP-PANIC-001"], "follow_up_questions": []})
add("P0122", one("green", ["CP-PANIC-002", "CP-PANIC-001"], "poor spelling and punctuation", PANIC_Q),
    prof(35, "female", ["panic disorder"]),
    "sudden dread in the supermarket queue, heart thumpin, legs shakin n fingers tinglin. sat in the car "
    "n it eased in about 10 mins. same as my other attacks",
    {"urgency": "green",
     "rationale": "Sudden dread with a pounding heart, trembling and tingling fingers, settling in ten "
                  "minutes and matching her previous attacks, in someone with diagnosed panic disorder. "
                  "The retrieved context lists those symptoms and says panic attacks themselves are not "
                  "life-threatening.",
     "red_flags": [],
     "next_steps": ["Do what worked here: somewhere quiet, and let it pass",
                    "Seek care the same day if one feels unlike your usual attacks"],
     "citations": ["CP-PANIC-002", "CP-PANIC-001"], "follow_up_questions": []})
add("P0123", one("green", ["CP-PANIC-001", "CP-PANIC-002"], "minimising the symptom",
                 {"CP-PANIC-001": [PANIC_ANYTIME, PANIC_LIKEHEART], "CP-PANIC-002": PANIC_PHYSICAL + [PANIC_NOTFATAL]}),
    prof(29, "male", ["panic attacks"]),
    "Nothing really. Woke with a jolt, heart going fast, felt out of control for twenty minutes, then it "
    "went. Happens every few weeks.",
    {"urgency": "green",
     "rationale": "Waking with a racing heart and a feeling of being out of control, resolving in twenty "
                  "minutes, recurring every few weeks in someone with known panic attacks. The retrieved "
                  "context says panic attacks can occur at any time including during sleep, lists these "
                  "physical symptoms, and says they are not life-threatening.",
     "red_flags": [],
     "next_steps": ["Keep a note of how often they happen and what precedes them",
                    "See your GP in the ordinary way if they are getting more frequent",
                    "Seek care the same day if one comes with chest pain that does not settle"],
     "citations": ["CP-PANIC-001", "CP-PANIC-002"], "follow_up_questions": []})

WALL_Q = {"CP-DIFF-001": [DIFF_NOTALWAYS, DIFF_MUSCLES, DIFF_IMMEDIATE]}
add("P0124", one("green", ["CP-DIFF-001"], "plain and factual", WALL_Q),
    prof(41, "male"),
    "Since a long day of decorating, the muscle down the front of my chest is tender. Reaching up to "
    "paint sets it off. Otherwise I am well and my breathing is normal.",
    {"urgency": "green",
     "rationale": "Chest wall tenderness after a day of unaccustomed overhead work, provoked by "
                  "reaching, in someone otherwise well. The retrieved context names sore "
                  "muscles among the causes of chest pain and says chest pain does not always mean a heart "
                  "attack. None of the features it sends for immediate care are present: the pain is not "
                  "constant, not crushing, and there is no nausea, sweating, dizziness or breathlessness.",
     "red_flags": [],
     "next_steps": ["Avoid overhead work for a few days and let the muscle settle",
                    "Seek assessment the same day if the pain becomes constant, or comes with "
                    "breathlessness, sweating or dizziness"],
     "citations": ["CP-DIFF-001"], "follow_up_questions": []})
add("P0125", one("green", ["CP-DIFF-001"], "verbose and anxious", WALL_Q),
    prof(36, "female"),
    "I am worried because the left side of my chest hurts, but it is only when I press a spot on my ribs "
    "or lift my arm, and it started after I moved furniture at the weekend. I can breathe fine. I have "
    "been reading about heart attacks and cannot stop thinking about it.",
    {"urgency": "green",
     "rationale": "Left-sided chest pain that appears only on pressing one spot or lifting the arm, after "
                  "moving furniture, with normal breathing. The retrieved context says chest pain does not "
                  "always mean a heart attack and names sore muscles among the causes, and none of the "
                  "features it sends for immediate care are present.",
     "red_flags": [],
     "next_steps": ["Avoid lifting for a few days and let the area settle",
                    "Seek assessment the same day if the pain becomes constant or comes with "
                    "breathlessness, sweating or dizziness"],
     "citations": ["CP-DIFF-001"], "follow_up_questions": []})
add("P0126", one("green", ["CP-DIFF-001"], "describing a third person", WALL_Q),
    prof(52, "male"),
    "My brother strained something shifting boxes at the weekend and now his chest hurts when he reaches "
    "up or presses the spot. He is otherwise well and breathing normally.",
    {"urgency": "green",
     "rationale": "Chest pain after lifting, provoked by reaching and pressing, in someone otherwise well. "
                  "The retrieved context names sore muscles among the causes of chest pain, and none of "
                  "the features it sends for immediate care are present.",
     "red_flags": [],
     "next_steps": ["Rest the area and avoid heavy lifting for a few days",
                    "Seek assessment the same day if it becomes constant or comes with breathlessness or "
                    "sweating"],
     "citations": ["CP-DIFF-001"], "follow_up_questions": []})
add("P0127", one("green", ["CP-DIFF-001"], "terse adult", WALL_Q),
    prof(24, "female"),
    "Chest wall sore since new gym programme. Worse pressing it. Breathing fine.",
    {"urgency": "green",
     "rationale": "Chest wall soreness since starting a new gym programme, worse on pressing, with normal "
                  "breathing. The retrieved context names sore muscles as a cause and none of its "
                  "immediate-care features are present.",
     "red_flags": [],
     "next_steps": ["Scale the programme back for a week",
                    "Seek assessment the same day if the pain becomes constant or comes with "
                    "breathlessness or dizziness"],
     "citations": ["CP-DIFF-001"], "follow_up_questions": []})

GERD_TARRY_Q = {"CP-GERD-001": [GERD_HEARTBURN, GERD_COMPLICATIONS], "CP-GERD-002": [GERD_TARRY]}
add("P0128", one("yellow", ["CP-GERD-001", "CP-GERD-002"], "minimising the symptom", GERD_TARRY_Q),
    prof(62, "male"),
    "Just my usual heartburn, though for the last two days my stools have looked black and tarry. I feel "
    "fine in myself.",
    {"urgency": "yellow",
     "rationale": "Usual reflux, but two days of black, tarry stools. The retrieved context lists stool "
                  "that looks black and tarry as a sign of bleeding in the digestive tract and says to "
                  "see a doctor for it. Feeling well does not change what the stool indicates.",
     "red_flags": ["Black tarry stools for two days"],
     "next_steps": ["Be seen today rather than waiting", "Go to an emergency department if you feel faint, "
                    "vomit blood, or the bleeding increases"],
     "citations": ["CP-GERD-001", "CP-GERD-002"],
     "follow_up_questions": ["Are you taking any anti-inflammatory tablets or blood thinners?"]})
add("P0129", one("yellow", ["CP-GERD-001", "CP-GERD-002"], "describing a third person", GERD_TARRY_Q),
    prof(47, "male"),
    "My partner has reflux and for two days his stools have been black and tarry. He has no pain apart "
    "from the usual burning after meals.",
    {"urgency": "yellow",
     "rationale": "Known reflux with two days of black, tarry stools. The retrieved context lists that as "
                  "a sign of bleeding in the digestive tract and says to see a doctor.",
     "red_flags": ["Black tarry stools for two days"],
     "next_steps": ["Get him seen today", "Go to an emergency department if he feels faint or vomits blood"],
     "citations": ["CP-GERD-001", "CP-GERD-002"],
     "follow_up_questions": ["Is he on any anti-inflammatory tablets?"]})

PERI_Q = {"CP-PERI-002": [PERI_PAIN], "CP-PERI-001": [PERI_CALL, PERI_VIRUS]}
add("P0130", one("yellow", ["CP-PERI-002", "CP-PERI-001"], "terse adult", PERI_Q),
    prof(29, "male"),
    "Stabbing pain behind the breastbone since Monday. Deep breaths make it worse, sitting forward "
    "settles it. Had a chest cold a fortnight ago. No breathlessness.",
    {"urgency": "yellow",
     "rationale": "Stabbing pain behind the breastbone since Monday, worse on deep breaths and settling "
                  "on sitting forward, a fortnight after a chest cold. The retrieved context describes "
                  "that pain pattern and says a virus can precede heart inflammation by a few weeks. No "
                  "breathlessness and not worsening, so assessment today.",
     "red_flags": ["Stabbing chest pain worse on deep breaths, eased sitting forward"],
     "next_steps": ["Be seen today", "Call emergency services if you become breathless at rest or the "
                    "pain gets worse"],
     "citations": ["CP-PERI-002", "CP-PERI-001"],
     "follow_up_questions": ["Any fever since the cold?"]})
add("P0131", one("yellow", ["CP-PERI-002", "CP-PERI-001"], "describing a third person", PERI_Q),
    prof(40, "female"),
    "My friend has had sharp chest pain since yesterday that gets worse when she breathes in and eases "
    "when she sits forward. She had a stomach bug last week. She is breathing comfortably.",
    {"urgency": "yellow",
     "rationale": "Sharp chest pain since yesterday, worse on breathing in and eased sitting forward, "
                  "after a gastrointestinal illness. The retrieved context describes that pain pattern and "
                  "says gastrointestinal symptoms can precede heart inflammation by a few weeks. She is "
                  "breathing comfortably, so assessment today.",
     "red_flags": ["Sharp chest pain worse on breathing in, eased sitting forward"],
     "next_steps": ["Get her assessed today", "Call emergency services if she becomes breathless at rest "
                    "or the pain worsens"],
     "citations": ["CP-PERI-002", "CP-PERI-001"],
     "follow_up_questions": ["Has she had a temperature with it?"]})
add("P0132", one("yellow", ["CP-PERI-002"], "minimising the symptom", {"CP-PERI-002": [PERI_PAIN]},
                 kind="grounding",
                 note="CP-PERI-002 lists Fast heartbeat and Fever, which this patient does not have. The "
                      "case omits them and red_flags must not contain them. Hard constraint 11 taught."),
    prof(33, "female"),
    "Probably pulled something, but for two days I have had a sharp pain in the middle of my chest that "
    "is worse when I breathe in and better when I lean forward.",
    {"urgency": "yellow",
     "rationale": "Two days of sharp central chest pain, worse on breathing in and better leaning "
                  "forward. That positional pattern matches the presentation in the retrieved context and "
                  "needs assessment today. The other findings listed there are not reported here.",
     "red_flags": ["Sharp central chest pain worse on breathing in, eased leaning forward"],
     "next_steps": ["Be seen today rather than waiting for it to settle",
                    "Call emergency services if you become breathless at rest"],
     "citations": ["CP-PERI-002"],
     "follow_up_questions": ["Have you had a temperature, or noticed your heart racing?"]})

add("P0133", one("yellow", ["CP-PNA-001"], "plain and factual", {"CP-PNA-001": PNA1_LIST}),
    prof(52, "male"),
    "Five days of fever and a cough bringing up green phlegm. My chest hurts on the right when I cough. "
    "Tired, but breathing normally.",
    {"urgency": "yellow",
     "rationale": "Five days of fever with a productive cough and one-sided chest pain on coughing, which "
                  "the retrieved context lists among the symptoms of pneumonia. Breathing is normal, so "
                  "this is assessment today.",
     "red_flags": ["Chest pain on coughing, after five days of fever"],
     "next_steps": ["Be seen by your GP today",
                    "Call emergency services if you become short of breath at rest or confused"],
     "citations": ["CP-PNA-001"],
     "follow_up_questions": ["Have you been able to keep fluids down?"]})
add("P0134", one("yellow", ["CP-PNA-001", "CP-PNA-002"], "minimising the symptom",
                 {"CP-PNA-001": PNA1_LIST, "CP-PNA-002": [PNA2_OTHER]}),
    prof(64, "female", ["type 2 diabetes"], ["metformin"]),
    "Just a chest infection, I think. Fever on and off for four days, coughing up yellow stuff, a bit "
    "sore when I cough. Breathing is fine.",
    {"urgency": "yellow",
     "rationale": "Four days of fever with a productive cough and chest pain on coughing in a woman with "
                  "diabetes. The retrieved context lists those symptoms for pneumonia and names diabetes "
                  "as an additional risk factor, which is why this needs assessment today rather than "
                  "waiting it out.",
     "red_flags": ["Fever on and off for four days, with chest pain on coughing"],
     "next_steps": ["Be seen by your GP today and mention the diabetes",
                    "Call emergency services if you become short of breath at rest or confused"],
     "citations": ["CP-PNA-001", "CP-PNA-002"],
     "follow_up_questions": ["Have your blood sugars been higher than usual?"]})

add("P0135", one("yellow", ["CP-PE-001", "CP-PE-004"], "plain and factual",
                 {"CP-PE-001": [VTE_LEG, VTE_CALL, VTE_AXIS], "CP-PE-004": [PE_OBESITY]}),
    prof(55, "female", ["obesity"]),
    "The back of my right leg below the knee has been puffy and sore to the touch since Monday, and my "
    "shoe feels tight. No chest pain, breathing normal.",
    {"urgency": "yellow",
     "rationale": "Several days of one-sided lower leg swelling that is sore to touch, with a tight "
                  "shoe. The retrieved context lists swollen, tender legs as the sign of a clot in the leg "
                  "veins, names obesity among the conditions that raise the risk, and says to call a "
                  "healthcare provider right away. No breathing symptoms.",
     "red_flags": ["Right lower leg puffy and sore to touch for days"],
     "next_steps": ["Get the leg assessed today",
                    "Call emergency services if you become short of breath or it hurts to breathe in"],
     "citations": ["CP-PE-001", "CP-PE-004"],
     "follow_up_questions": ["Is only the one leg affected?"]})
add("P0136", one("yellow", ["CP-PE-001", "CP-PE-004"], "terse adult",
                 {"CP-PE-001": [VTE_LEG, VTE_CALL], "CP-PE-004": [PE_KIDNEY]}),
    prof(47, "male", ["chronic kidney disease"]),
    "Right calf swollen and tender since Friday. Breathing normal. No chest pain.",
    {"urgency": "yellow",
     "rationale": "One-sided calf swelling and tenderness since Friday. The retrieved context lists "
                  "swollen, tender legs as the sign of a clot in the leg veins, names kidney disease among "
                  "the conditions that make the blood clot more easily, and says to call a healthcare "
                  "provider right away.",
     "red_flags": ["Right calf swollen and tender for days"],
     "next_steps": ["Get it assessed today",
                    "Call emergency services if you become breathless or it hurts to breathe in"],
     "citations": ["CP-PE-001", "CP-PE-004"],
     "follow_up_questions": ["Any recent travel, surgery or time off your feet?"]})

add("P0137", one("yellow", ["CP-ANG-005", "CP-ANG-009"], "describing a third person",
                 {"CP-ANG-005": [ANG5_EXERTION, ANG5_REST, ANG5_5MIN], "CP-ANG-009": [ANG9_STABLE]}),
    prof(73, "male", ["coronary artery disease", "angina"], ["atorvastatin"]),
    "My dad's angina came on walking up the stairs to bed. He sat on the stairs and it went within three "
    "minutes, the way it always does.",
    {"urgency": "yellow",
     "rationale": "Known angina brought on by climbing stairs and gone within three minutes of sitting, "
                  "in the pattern he recognises. The retrieved context gives exertional pain relieved by "
                  "rest, going within five minutes, as the stable pattern. It still warrants review.",
     "red_flags": ["Chest pain on climbing stairs in known angina, settling with rest"],
     "next_steps": ["Arrange a GP review for him today",
                    "Call emergency services if an episode comes on at rest or does not settle when he stops"],
     "citations": ["CP-ANG-005", "CP-ANG-009"],
     "follow_up_questions": ["Is he getting them on fewer stairs than before?"]})

add("P0138", one("red", ["CP-DIFF-001", "CP-ACS-003"], "plain and factual",
                 {"CP-DIFF-001": [DIFF_IMMEDIATE], "CP-ACS-003": [ACS3_LIST[0], ACS3_LIST[2]]}),
    prof(50, "male"),
    "Chest pain for the last half hour with sweating and dizziness. It started while I was sitting at my "
    "desk.",
    {"urgency": "red",
     "rationale": "Half an hour of chest pain that began at rest, with sweating and dizziness. The "
                  "retrieved context says to get immediate medical care for chest pain that does not go "
                  "away or chest pain along with sweating or dizziness, and lists central chest pain and "
                  "sweating for no reason among heart attack symptoms.",
     "red_flags": ["Chest pain unchanged for half an hour, started at rest",
                   "Sweating and dizziness with the chest pain"],
     "next_steps": ["Call emergency services now", "Sit still and unlock the door for the crew",
                    "Do not drive yourself"],
     "citations": ["CP-DIFF-001", "CP-ACS-003"], "follow_up_questions": []},
    "T+0:00 chest pain began sitting at a desk. T+0:10 sweating and dizziness. T+0:30 unchanged.")
add("P0139", one("red", ["CP-ACS-003", "CP-ACS-005"], "poor spelling and punctuation",
                 {"CP-ACS-003": [ACS3_LIST[0], ACS3_LIST[1], ACS3_LIST[2], ACS3_LIST[3]],
                  "CP-ACS-005": [ACS5_NOTGOAWAY]}),
    prof(57, "male", ["high blood pressure"], ["amlodipine"]),
    "crushin pain middle of my chest 30 mins now, goin down my left arm, sweatin n i feel sick",
    {"urgency": "red",
     "rationale": "Half an hour of crushing central chest pain radiating to the left arm, with sweating "
                  "and nausea, unrelieved. The retrieved context lists central chest pain, pain going into "
                  "the arm, sweating for no reason and nausea among heart attack symptoms, and says heart "
                  "attack pain does not go away with rest.",
     "red_flags": ["Crushing central chest pain for 30 minutes, radiating to the left arm",
                   "Sweating and feeling sick with the chest pain"],
     "next_steps": ["Call emergency services now", "Do not drive yourself to hospital",
                    "Sit down and stay still"],
     "citations": ["CP-ACS-003", "CP-ACS-005"], "follow_up_questions": []},
    "T+0:00 crushing central pain began. T+0:10 spread to the left arm, sweating. T+0:30 unchanged.")
add("P0140", one("red", ["CP-ACS-005", "CP-ANG-005"], "verbose and anxious",
                 {"CP-ACS-005": [ACS5_NOTGOAWAY, ACS5_CALL], "CP-ANG-005": [ANG5_REST, ANG5_5MIN]}),
    prof(59, "male", ["angina"], ["bisoprolol"]),
    "I have angina, so I am used to this, but honestly I cannot tell whether this is it or something "
    "worse. It came on walking, I stopped ten minutes ago and it is still there, which is not how mine "
    "usually behaves.",
    {"urgency": "red",
     "rationale": "Chest pain in known angina that has not resolved ten minutes after stopping, and he "
                  "cannot tell whether it is his angina. The retrieved context says heart attack pain does "
                  "not go away with rest, that his stable pattern should go within five minutes, and that "
                  "if you do not know whether chest pain is angina or a heart attack you should call "
                  "9-1-1.",
     "red_flags": ["Chest pain persisting ten minutes after stopping, unlike his usual angina"],
     "next_steps": ["Call emergency services now", "Do not drive yourself",
                    "Sit down and stay where you are until the ambulance arrives"],
     "citations": ["CP-ACS-005", "CP-ANG-005"], "follow_up_questions": []},
    "T+0:00 chest pain began walking. T+0:02 stopped walking. T+0:12 still present.")
