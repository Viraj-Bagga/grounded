"""PRIORITY 1: contrast sets, 2026-09-19, against the 35-chunk corpus.

Rebuilds the sets for the conditions where every pair shared one verdict, and
adds the angina equivalents the new chunks make possible. Every axis quotes the
line that draws the distinction, from a chunk BOTH halves cite (constraint 14).

CP-PANIC and CP-PLEU get no set. CP-PANIC-002 states that panic attacks
themselves are not life-threatening, which contradicts a yellow or red half, and
CP-PLEU-001 gives pleurisy no disposition at all. Both are recorded in
01-data/eval/heldout-eval/README.md. Neither can be fixed with a case; each
needs a source.

Two halves differ in the discriminator and in nothing else: same profile, same
register, same chunks, same history.
"""


def prof(age, sex, conditions=(), medications=()):
    return (f"age: {age}, sex: {sex}\n"
            f"conditions: {', '.join(conditions) or 'none'}\n"
            f"medications: {', '.join(medications) or 'none'}")


# --- the lines each axis turns on, quoted once ------------------------------
VTE_AXIS = ("Deep vein thrombosis (DVT) should be taken seriously, as it may "
            "lead to a life-threatening pulmonary embolism (PE).")
VTE_LEG = ("Swollen and tender legs that are painful to the touch, if you have "
           "blood clots that block blood flow to your leg veins ( deep vein "
           "thrombosis or DVT )")
VTE_LUNG = ("Shortness of breath and pain when breathing, if you have a blood "
            "clot that travels to the lungs ( pulmonary embolism )")
VTE_CALL = ("Call your healthcare provider right away if you think you may "
            "have symptoms of VTE.")
PE_BEDREST = ("Especially when combined with other risk factors, DVT can "
              "develop during a long flight (more than 4 hours) or when a "
              "person is on bed rest in a nursing home, hospital setting, or "
              "after surgery.")
PE_STILL = ("Being still slows blood flow through the veins in your arms and "
            "legs, raising the likelihood of DVT.")
PE_CANCER = "cancer and cancer treatments including chemotherapy and surgery"
DIFF_IMMEDIATE = ("Get immediate medical care if you have chest pain that does "
                  "not go away, crushing pain or pressure in the chest, or "
                  "chest pain along with nausea, sweating, dizziness or "
                  "shortness of breath.")
PNA_SYMPTOMS = "Chest pain when you breathe or cough"
PNA_RISK = ("Young children, older adults, and people who have serious health "
            "conditions are at risk for developing more serious pneumonia or "
            "life-threatening complications.")
PNA_CONFUSED = ("Older adults who have pneumonia may feel weak or suddenly "
                "confused.")
ANG_STABLE_EXERTION = "Pain that occurs during physical activity or mental stress"
ANG_STABLE_5MIN = "Symptoms that go away within 5 minutes"
ANG_STABLE_REST = "Pain that is relieved by rest or medicines"
ANG_UNSTABLE_REST = "Pain during rest or sleep"
ANG_UNSTABLE_20MIN = ("Pain that lasts longer than 20 minutes or goes away and "
                      "then comes back")
ANG_EMERGENCY = ("Unstable angina is a medical emergency because it can "
                 "progress to a heart attack .")
ANG_INDIGESTION = "Heartburn or indigestion"
GERD_HEARTBURN = ("heartburn , a painful, burning feeling in the middle of your "
                  "chest, behind your breastbone, rising from the lower tip of "
                  "your breastbone toward your throat")

PAIRS = {}


def add(pid, slot, profile, symptoms, answer, timeline=None):
    PAIRS[pid] = {"slot": slot, "profile": profile, "symptoms": symptoms,
                  "answer": answer, **({"timeline": timeline} if timeline else {})}


def contrast(cid, axis, keys, register, quotes, axis_quote):
    def slot(pid, cat, side):
        return {"kind": "contrast", "target_category": cat, "reference_keys": list(keys),
                "register": register, "contrast_id": cid, "contrast_axis": axis,
                "contrast_side": side, "axis_quote": axis_quote, "quotes": quotes}
    return slot


# ===========================================================================
# CP-PE. Axis: have breathing symptoms joined the swollen leg. The risk factor
# is held constant and present in BOTH halves, so the set teaches the lungs and
# not the risk factor.
# ===========================================================================
_pe13 = contrast("C13", "have breathing symptoms joined the swollen leg",
                 ["CP-PE-001", "CP-PE-003"], "plain and factual",
                 {"CP-PE-001": [VTE_AXIS, VTE_LEG, VTE_LUNG, VTE_CALL], "CP-PE-003": [PE_BEDREST]},
                 {"CP-PE-001": VTE_AXIS})
add("P0061", _pe13("P0061", "yellow", "swollen tender calf after a week of bed rest, breathing normal"),
    prof(57, "female"),
    "I came home three days ago after a week in hospital with a slipped disc, mostly lying flat. "
    "Since yesterday my left calf has swollen up and it is tender when I touch it. My breathing is "
    "normal and I have no chest pain.",
    {"urgency": "yellow",
     "rationale": "A newly swollen, tender calf three days after a week of bed rest in hospital. The "
                  "retrieved context lists swollen, tender legs as the sign of a clot blocking the leg "
                  "veins, names bed rest in a hospital setting among the causes, and says to call a "
                  "healthcare provider right away. Breathing is normal with no chest pain, so nothing "
                  "points to a clot in the lungs.",
     "red_flags": ["Left calf swollen and tender since yesterday, after a week in bed"],
     "next_steps": ["Get the leg assessed today, by your GP or an urgent care service",
                    "Call emergency services if you become short of breath or it hurts to breathe in"],
     "citations": ["CP-PE-001", "CP-PE-003"],
     "follow_up_questions": ["Is the swelling in one leg only?"]},
    "T+0:00 calf ache noticed yesterday morning. T+24:00 calf swollen and tender to touch.")
add("P0062", _pe13("P0062", "red", "swollen tender calf after a week of bed rest, now breathless with pain on breathing in"),
    prof(57, "female"),
    "I came home three days ago after a week in hospital with a slipped disc, mostly lying flat. "
    "Since yesterday my left calf has swollen up and it is tender when I touch it. This morning I "
    "became short of breath, and it hurts when I breathe in.",
    {"urgency": "red",
     "rationale": "A swollen, tender calf after a week of bed rest in hospital, now with breathlessness "
                  "and pain on breathing in. The retrieved context names shortness of breath and pain "
                  "when breathing as the signs of a clot that has travelled to the lungs, and calls "
                  "pulmonary embolism life-threatening.",
     "red_flags": ["Short of breath since this morning, with a swollen tender calf",
                   "Pain on breathing in, new this morning"],
     "next_steps": ["Call emergency services now", "Do not drive yourself to hospital",
                    "Sit upright and stay with someone until help arrives"],
     "citations": ["CP-PE-001", "CP-PE-003"],
     "follow_up_questions": []},
    "T+0:00 calf ache noticed yesterday morning. T+24:00 calf swollen and tender to touch. "
    "T+26:00 short of breath, pain on breathing in.")

_pe14 = contrast("C14", "have breathing symptoms joined the swollen leg",
                 ["CP-PE-001", "CP-PE-004"], "terse adult",
                 {"CP-PE-001": [VTE_AXIS, VTE_LEG, VTE_LUNG, VTE_CALL], "CP-PE-004": [PE_CANCER]},
                 {"CP-PE-001": VTE_AXIS})
add("P0063", _pe14("P0063", "yellow", "swollen tender calf during chemotherapy, breathing normal"),
    prof(63, "male", ["bowel cancer"], ["chemotherapy"]),
    "Midway through chemo for bowel cancer. Right leg swollen over two days, calf sore to press. "
    "Breathing fine. No chest pain.",
    {"urgency": "yellow",
     "rationale": "Two days of one-sided leg swelling with a calf that is sore to press, during "
                  "chemotherapy. The retrieved context lists swollen, tender legs as the sign of a clot "
                  "in the leg veins and names cancer and chemotherapy among the conditions that raise "
                  "the risk, and it says to call a healthcare provider right away. No breathing "
                  "symptoms, so nothing points to the lungs.",
     "red_flags": ["Right leg swollen over two days, calf sore to press"],
     "next_steps": ["Ring the oncology team or your GP today and ask to be seen",
                    "Call emergency services if you become short of breath or it hurts to breathe in"],
     "citations": ["CP-PE-001", "CP-PE-004"],
     "follow_up_questions": ["Is the swelling in one leg only?"]},
    "T+0:00 leg swelling noticed two days ago. T+48:00 calf sore to press.")
add("P0064", _pe14("P0064", "red", "swollen tender calf during chemotherapy, now breathless with pain on breathing in"),
    prof(63, "male", ["bowel cancer"], ["chemotherapy"]),
    "Midway through chemo for bowel cancer. Right leg swollen over two days, calf sore to press. "
    "Last hour, short of breath and chest hurts when I breathe in.",
    {"urgency": "red",
     "rationale": "One-sided leg swelling during chemotherapy, now with breathlessness and pain on "
                  "breathing in within the last hour. The retrieved context names those two as the signs "
                  "of a clot that has travelled to the lungs and calls pulmonary embolism "
                  "life-threatening. Cancer and chemotherapy are named risk factors.",
     "red_flags": ["Short of breath within the last hour, with a swollen leg",
                   "Chest pain on breathing in, new in the last hour"],
     "next_steps": ["Call emergency services now", "Do not drive yourself to hospital"],
     "citations": ["CP-PE-001", "CP-PE-004"],
     "follow_up_questions": []},
    "T+0:00 leg swelling noticed two days ago. T+48:00 calf sore to press. "
    "T+49:00 short of breath, chest pain on breathing in.")

_pe15 = contrast("C15", "have breathing symptoms joined the swollen leg",
                 ["CP-PE-001", "CP-PE-003"], "describing a third person",
                 {"CP-PE-001": [VTE_AXIS, VTE_LEG, VTE_LUNG, VTE_CALL], "CP-PE-003": [PE_STILL]},
                 {"CP-PE-001": VTE_AXIS})
add("P0065", _pe15("P0065", "yellow", "swollen tender calf above a plaster cast, breathing normal"),
    prof(38, "female"),
    "My sister broke her ankle three weeks ago and her leg is in plaster, so she is barely moving. "
    "Her calf above the plaster has gone swollen and it is sore when she touches it. She is breathing "
    "normally and has no chest pain.",
    {"urgency": "yellow",
     "rationale": "A swollen, tender calf in a leg that has been immobilised in plaster for three weeks. "
                  "The retrieved context says being still slows blood flow in the legs and raises the "
                  "likelihood of a clot, lists swollen, tender legs as the sign of one, and says to call "
                  "a healthcare provider right away. Her breathing is normal.",
     "red_flags": ["Calf above the cast swollen and sore to touch, three weeks immobile"],
     "next_steps": ["Get her leg assessed today, by her GP or an urgent care service",
                    "Call emergency services if she becomes short of breath or it hurts her to breathe in"],
     "citations": ["CP-PE-001", "CP-PE-003"],
     "follow_up_questions": ["Is the swelling only in the leg that is in plaster?"]})
add("P0066", _pe15("P0066", "red", "swollen tender calf above a plaster cast, now breathless with pain on breathing in"),
    prof(38, "female"),
    "My sister broke her ankle three weeks ago and her leg is in plaster, so she is barely moving. "
    "Her calf above the plaster has gone swollen and it is sore when she touches it. In the last half "
    "hour she has become short of breath and says it hurts to breathe in.",
    {"urgency": "red",
     "rationale": "A swollen, tender calf in a leg immobilised for three weeks, now with breathlessness "
                  "and pain on breathing in within the last half hour. The retrieved context names those "
                  "as the signs of a clot that has reached the lungs and calls pulmonary embolism "
                  "life-threatening.",
     "red_flags": ["Short of breath in the last half hour, with a swollen calf",
                   "Pain on breathing in, new in the last half hour"],
     "next_steps": ["Call emergency services now", "Keep her sitting upright and stay with her"],
     "citations": ["CP-PE-001", "CP-PE-003"],
     "follow_up_questions": []})

# ===========================================================================
# CP-PNA. Two axes: breathlessness alongside the chest pain, and sudden
# confusion in an older adult. Everything else is held constant in each set.
# ===========================================================================
_pna16 = contrast("C16", "is there breathlessness alongside the chest pain",
                  ["CP-PNA-001", "CP-DIFF-001"], "verbose and anxious",
                  {"CP-PNA-001": [PNA_SYMPTOMS, "Cough with or without mucus", "Fever", "Shortness of breath"],
                   "CP-DIFF-001": [DIFF_IMMEDIATE]},
                  {"CP-DIFF-001": DIFF_IMMEDIATE})
add("P0067", _pna16("P0067", "yellow", "four days of fever and productive cough with chest pain on coughing, breathing comfortably"),
    prof(44, "male"),
    "I am sorry to message so late. I have had a fever and a cough bringing up thick phlegm for four "
    "days now, and my chest hurts on the left every time I cough. My breathing feels normal though, I "
    "can walk around and talk fine. I am just worried it is turning into something.",
    {"urgency": "yellow",
     "rationale": "Four days of fever with a productive cough and chest pain on coughing, which the "
                  "retrieved context lists among the symptoms of pneumonia. Breathing is comfortable, so "
                  "none of the features the context sends for immediate care are present, but this needs "
                  "assessment today.",
     "red_flags": ["Chest pain on coughing, after four days of fever"],
     "next_steps": ["Be seen today by your GP or an urgent care service",
                    "Call emergency services if you become short of breath at rest"],
     "citations": ["CP-PNA-001", "CP-DIFF-001"],
     "follow_up_questions": ["Have you measured your temperature today?"]},
    "T+0:00 fever and cough began four days ago. T+72:00 phlegm thicker, chest pain on coughing. "
    "T+96:00 unchanged, breathing comfortable.")
add("P0068", _pna16("P0068", "red", "four days of fever and productive cough with chest pain on coughing, now short of breath at rest"),
    prof(44, "male"),
    "I am sorry to message so late. I have had a fever and a cough bringing up thick phlegm for four "
    "days now, and my chest hurts on the left every time I cough. Tonight I am short of breath even "
    "sitting still. I am really worried.",
    {"urgency": "red",
     "rationale": "Four days of fever with a productive cough and chest pain on coughing, now with "
                  "breathlessness at rest. The retrieved context says chest pain along with shortness of "
                  "breath needs immediate medical care, and lists both among the symptoms of pneumonia.",
     "red_flags": ["Short of breath at rest tonight", "Chest pain on coughing, after four days of fever"],
     "next_steps": ["Call emergency services now", "Sit upright while you wait"],
     "citations": ["CP-PNA-001", "CP-DIFF-001"],
     "follow_up_questions": []},
    "T+0:00 fever and cough began four days ago. T+72:00 phlegm thicker, chest pain on coughing. "
    "T+96:00 short of breath sitting still.")

_pna17 = contrast("C17", "has an older adult become suddenly confused",
                  ["CP-PNA-001"], "panicked caregiver",
                  {"CP-PNA-001": [PNA_RISK, PNA_CONFUSED, PNA_SYMPTOMS, "Fever"]},
                  {"CP-PNA-001": PNA_CONFUSED})
add("P0069", _pna17("P0069", "yellow", "three days of cough and fever with chest pain on coughing, alert and himself"),
    prof(79, "male", ["high blood pressure"], ["amlodipine"]),
    "Dad has had a cough and a fever for three days and his chest hurts when he coughs. He is still "
    "himself, chatting away and eating a bit, and his breathing is fine. I just do not know whether he "
    "needs seeing!",
    {"urgency": "yellow",
     "rationale": "Three days of cough and fever with chest pain on coughing in a 79-year-old. The "
                  "retrieved context lists those symptoms for pneumonia and names older adults as at "
                  "risk of more serious pneumonia. He is alert and breathing comfortably, so this needs "
                  "assessment today rather than emergency care.",
     "red_flags": ["Chest pain on coughing, after three days of fever"],
     "next_steps": ["Get him seen by his GP today",
                    "Call emergency services if he becomes confused, drowsy or short of breath"],
     "citations": ["CP-PNA-001"],
     "follow_up_questions": ["Is he drinking enough, and passing urine as usual?"]},
    "T+0:00 cough and fever began three days ago. T+72:00 alert, eating, breathing comfortably.")
add("P0070", _pna17("P0070", "red", "three days of cough and fever with chest pain on coughing, now suddenly confused"),
    prof(79, "male", ["high blood pressure"], ["amlodipine"]),
    "Dad has had a cough and a fever for three days and his chest hurts when he coughs. Since this "
    "morning he is confused, he does not know what day it is and he keeps calling me by my brother's "
    "name. His breathing is fine. Please help!",
    {"urgency": "red",
     "rationale": "Three days of cough and fever with chest pain on coughing in a 79-year-old, and since "
                  "this morning he is confused. The retrieved context says older adults with pneumonia "
                  "may become suddenly confused, and names older adults as at risk of life-threatening "
                  "complications.",
     "red_flags": ["Confused since this morning, after three days of fever and cough"],
     "next_steps": ["Call emergency services now", "Stay with him and keep him sitting up"],
     "citations": ["CP-PNA-001"],
     "follow_up_questions": []},
    "T+0:00 cough and fever began three days ago. T+72:00 confused, does not know the day.")

# ===========================================================================
# ANGINA. The equivalents the new chunks make possible: onset at rest, and
# duration past the stable threshold. Both halves of each set are a known
# angina pattern, so the only thing that moves is the discriminator.
# ===========================================================================
_ang18 = contrast("C18", "did the episode come on at rest or on exertion",
                  ["CP-ANG-005", "CP-ANG-006", "CP-ANG-010"], "plain and factual",
                  {"CP-ANG-005": [ANG_STABLE_EXERTION, ANG_STABLE_REST, ANG_STABLE_5MIN],
                   "CP-ANG-006": [ANG_UNSTABLE_REST], "CP-ANG-010": [ANG_EMERGENCY]},
                  {"CP-ANG-006": ANG_UNSTABLE_REST})
add("P0071", _ang18("P0071", "yellow", "known angina brought on by exertion, gone within five minutes"),
    prof(66, "male", ["coronary artery disease"], ["aspirin", "ramipril"]),
    "Pushing the lawnmower this afternoon I got my usual angina tightness across my chest. I stopped "
    "and it went within about five minutes.",
    {"urgency": "yellow",
     "rationale": "Known angina brought on by exertion and gone within five minutes of stopping. The "
                  "retrieved context gives exactly that as the stable pattern: pain during physical "
                  "activity, relieved by rest, going within five minutes. None of the features it lists "
                  "for unstable angina are present.",
     "red_flags": ["Chest tightness on exertion in known coronary artery disease"],
     "next_steps": ["Arrange to be seen by your GP or heart team today",
                    "Call emergency services if an episode comes on at rest, or does not go when you stop"],
     "citations": ["CP-ANG-005", "CP-ANG-006"],
     "follow_up_questions": ["Has it started coming on with less effort than before?"]},
    "T+0:00 tightness began pushing the lawnmower. T+0:01 stopped. T+0:05 gone.")
add("P0072", _ang18("P0072", "red", "known angina coming on at rest, gone within five minutes"),
    prof(66, "male", ["coronary artery disease"], ["aspirin", "ramipril"]),
    "Sitting reading the paper this afternoon I got my usual angina tightness across my chest, without "
    "doing anything at all. It went within about five minutes.",
    {"urgency": "red",
     "rationale": "The same angina tightness, but it came on at rest rather than on exertion. The "
                  "retrieved context lists pain during rest as a feature of unstable angina, and says "
                  "unstable angina is a medical emergency because it can progress to a heart attack. "
                  "That it settled in five minutes does not undo the change in pattern.",
     "red_flags": ["Angina tightness came on at rest, with no exertion"],
     "next_steps": ["Call emergency services now", "Do not drive yourself to hospital",
                    "Sit still and stay where you are"],
     "citations": ["CP-ANG-006", "CP-ANG-010"],
     "follow_up_questions": []},
    "T+0:00 tightness began sitting reading. T+0:05 gone.")

_ang19 = contrast("C19", "did it settle within five minutes or last beyond twenty",
                  ["CP-ANG-005", "CP-ANG-006", "CP-ANG-010"], "describing a third person",
                  {"CP-ANG-005": [ANG_STABLE_5MIN, ANG_STABLE_REST],
                   "CP-ANG-006": [ANG_UNSTABLE_20MIN], "CP-ANG-010": [ANG_EMERGENCY]},
                  {"CP-ANG-006": ANG_UNSTABLE_20MIN})
add("P0073", _ang19("P0073", "yellow", "exertional angina that settled within five minutes of standing still"),
    prof(71, "female", ["angina"], ["bisoprolol"]),
    "My mum gets her angina walking to the bus stop. It started again this morning on the way, she "
    "stood still, and it had gone within five minutes, the way it usually does.",
    {"urgency": "yellow",
     "rationale": "Exertional angina in a known pattern that resolved within five minutes of stopping. "
                  "The retrieved context gives relief with rest and symptoms going within five minutes "
                  "as the stable pattern. Angina still warrants review, but nothing here matches the "
                  "unstable features it lists.",
     "red_flags": ["Chest pain on walking in known angina, settling with rest"],
     "next_steps": ["Arrange a GP appointment for her today",
                    "Call emergency services if an episode lasts more than twenty minutes or comes on at rest"],
     "citations": ["CP-ANG-005", "CP-ANG-006"],
     "follow_up_questions": ["Is she getting them more often than she used to?"]},
    "T+0:00 tightness began walking to the bus stop. T+0:01 stood still. T+0:05 gone.")
add("P0074", _ang19("P0074", "red", "exertional angina still present forty minutes after stopping"),
    prof(71, "female", ["angina"], ["bisoprolol"]),
    "My mum gets her angina walking to the bus stop. It started again this morning on the way, she "
    "stood still, and it is still there now, forty minutes later, even sitting down.",
    {"urgency": "red",
     "rationale": "Exertional angina that has not resolved forty minutes after stopping. The retrieved "
                  "context lists pain lasting longer than twenty minutes as a feature of unstable "
                  "angina, against a stable pattern that goes within five minutes, and says unstable "
                  "angina is a medical emergency.",
     "red_flags": ["Angina unchanged forty minutes after stopping and sitting down"],
     "next_steps": ["Call emergency services now", "Do not drive her to hospital, wait for the ambulance",
                    "Keep her sitting still"],
     "citations": ["CP-ANG-005", "CP-ANG-006", "CP-ANG-010"],
     "follow_up_questions": []},
    "T+0:00 tightness began walking to the bus stop. T+0:01 stood still. T+0:40 unchanged, sitting down.")

# ===========================================================================
# The ACS mimic, both ways round. Same burning behind the breastbone; what
# separates them is what brings it on. Both halves cite the reflux chunk and the
# angina chunks, so neither verdict can be read off which chunk arrived.
# ===========================================================================
_mimic20 = contrast("C20", "is the burning brought on by meals or by exertion",
                    ["CP-GERD-001", "CP-ANG-003", "CP-ANG-005"], "plain and factual",
                    {"CP-GERD-001": [GERD_HEARTBURN], "CP-ANG-003": [ANG_INDIGESTION],
                     "CP-ANG-005": [ANG_STABLE_EXERTION, ANG_STABLE_REST]},
                    {"CP-ANG-005": ANG_STABLE_EXERTION})
add("P0075", _mimic20("P0075", "green", "indigestion-like burning after large meals, worse lying down, eased sitting up"),
    prof(57, "male"),
    "For about three months I have had a burning feeling behind my breastbone, like indigestion, "
    "lasting a few minutes. It comes on after big evening meals, especially when I lie down, and it "
    "eases when I sit up.",
    {"urgency": "green",
     "rationale": "Burning behind the breastbone after large meals, worse lying down and eased sitting "
                  "up, over three months. The retrieved context describes that as heartburn from reflux. "
                  "It is not brought on by exertion and not relieved by rest, which is the angina "
                  "pattern the same context describes, and the context notes angina can feel like "
                  "indigestion.",
     "red_flags": [],
     "next_steps": ["Try smaller evening meals and leave a few hours before lying down",
                    "Raise the head of the bed if the night-time burning continues",
                    "Seek assessment today if it starts coming on when you walk or exert yourself"],
     "citations": ["CP-GERD-001", "CP-ANG-005"],
     "follow_up_questions": []})
add("P0076", _mimic20("P0076", "yellow", "indigestion-like burning brought on by walking uphill, eased by stopping"),
    prof(57, "male"),
    "For about three months I have had a burning feeling behind my breastbone, like indigestion, "
    "lasting a few minutes. It comes on when I walk up the hill to work and it eases when I stand "
    "still for a bit.",
    {"urgency": "yellow",
     "rationale": "The same indigestion-like burning, but brought on by walking uphill and relieved by "
                  "standing still. The retrieved context says angina can feel like heartburn or "
                  "indigestion, and gives pain that comes with physical activity and is relieved by rest "
                  "as the angina pattern. It has never been assessed, so it needs seeing.",
     "red_flags": ["Burning behind the breastbone brought on by walking uphill, eased by rest"],
     "next_steps": ["Arrange to be seen by your GP today",
                    "Call emergency services if it comes on at rest or does not ease when you stop"],
     "citations": ["CP-ANG-003", "CP-ANG-005"],
     "follow_up_questions": ["Does it ever spread to your arm, neck or jaw?"]})
