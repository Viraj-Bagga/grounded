"""PRIORITY 2: pairs the 13 appended chunks make possible, 2026-09-19.

None of these could be written against the 22-chunk corpus, because the chunk
that grounds each one was appended on 2026-09-19:

  CP-ACS-006  heart attack in women, and the call-9-1-1 line for those symptoms
  CP-ANG-003  the angina symptom list, including heartburn or indigestion
  CP-ANG-004  angina in women: arms, neck, back and jaw
  CP-ANG-005  the stable angina criteria, as thresholds
  CP-ANG-006  the unstable angina criteria, as thresholds
  CP-ANG-007  microvascular angina
  CP-ANG-008  vasospastic angina
  CP-ANG-009  stable angina prose, and the pattern-change line
  CP-ANG-010  unstable angina is a medical emergency
  CP-ANG-011  microvascular angina prose
  CP-ANG-012  vasospastic angina prose
  CP-PNA-002  what raises pneumonia risk: COPD, steroids, heart failure
  CP-PNA-003  pneumonia can look like a cold until it outlasts one

Every quote is verbatim. No pair here turns on a change in the angina pattern:
CP-ANG-006 lists that as unstable while CP-ANG-009 says tell your provider right
away, so the corpus disagrees with itself and it is not a safe criterion.
"""


def prof(age, sex, conditions=(), medications=()):
    return (f"age: {age}, sex: {sex}\n"
            f"conditions: {', '.join(conditions) or 'none'}\n"
            f"medications: {', '.join(medications) or 'none'}")


ACS6_LIST = ["Pain in the shoulder, back, or arm", "Shortness of breath",
             "Unusual tiredness and weakness", "Upset stomach", "Anxiety"]
ACS6_EITHER = "These symptoms can happen together with chest pain or without any chest pain."
ACS6_CALL = "It is important to call 9-1-1 if you have these symptoms."
ACS2_SILENT = ("Silent heart attacks are more common in older adults and in people who have high blood "
               "sugar or diabetes.")
ACS3_REST_SOB = ("Shortness of breath when resting or doing a little bit of physical activity (this is "
                 "more common in older adults)")
ANG3_CALL = "Call 9-1-1 if you feel chest discomfort that does not go away with rest or medicine."
ANG3_SPREAD = ("The pain or discomfort can also be felt in areas far from the source of the pain, such "
               "as the shoulders, arms, neck, back, and jaw.")
ANG3_INDIGESTION = "Heartburn or indigestion"
ANG4_WOMEN = ("It is more common for women to feel angina pain in the arms, neck, back, and jaw — areas "
              "far from the source of the pain.")
ANG4_OTHER = ("Women also more often show other symptoms of angina aside from chest pain, such as "
              "shortness of breath, nausea, and light-headedness.")
ANG5_EXERTION = "Pain that occurs during physical activity or mental stress"
ANG5_REST = "Pain that is relieved by rest or medicines"
ANG5_5MIN = "Symptoms that go away within 5 minutes"
ANG5_PATTERN = "Pattern of symptoms that has not changed in the last 2 months"
ANG6_REST = "Pain during rest or sleep"
ANG6_20MIN = "Pain that lasts longer than 20 minutes or goes away and then comes back"
ANG6_NOTRELIEVED = "Pain that is not relieved by rest or medicines"
ANG6_INTENSE = "Intense pain"
ANG7_LIST = ["Intense pain", "Pain that lasts a long time", "Shortness of breath",
             "Pain that happens during physical or emotional stress or during rest"]
ANG8_LIST = ["Pain that starts at night or in the early morning hours",
             "Pattern of symptoms that happen during rest or sleep",
             "Symptoms that last around 15 minutes"]
ANG9_STABLE = ("If you have stable angina, you can learn its pattern and predict when an event will "
               "occur, such as during physical activity or mental stress.")
ANG10_EMERGENCY = "Unstable angina is a medical emergency because it can progress to a heart attack ."
ANG10_NOPATTERN = ("Unstable angina does not follow a pattern. It may be new or occur more often and be "
                   "more painful than stable angina.")
ANG11_MICRO = ("Microvascular angina events can be stable or unstable, and they can be more painful and "
               "last longer than other types of angina.")
ANG12_SPASM = ("This type of angina usually happens while you are at rest, between midnight and early "
               "morning, and in a pattern.")
PNA1_LIST = ["Chest pain when you breathe or cough", "Cough with or without mucus", "Fever", "Chills"]
PNA1_RISK = ("Young children, older adults, and people who have serious health conditions are at risk "
             "for developing more serious pneumonia or life-threatening complications.")
PNA2_LUNG = ("Lung diseases, such as asthma , bronchiectasis , cystic fibrosis , or COPD , also increase "
             "your pneumonia risk.")
PNA2_STEROID = ("Chemotherapy, which is used to treat cancer, and long-term use of steroid medicines can "
                "also weaken your immune system.")
PNA2_OTHER = ("Other serious conditions, such as malnutrition, diabetes , heart failure , sickle cell "
              "disease , or liver or kidney disease, are additional risk factors.")
PNA3_COLD = ("You may not realize that your condition is more serious until it lasts longer than these "
             "other conditions.")

PAIRS = {}


def add(pid, cat, keys, register, quotes, profile, symptoms, answer, timeline=None, kind="standalone"):
    PAIRS[pid] = {"slot": {"kind": kind, "target_category": cat, "reference_keys": list(keys),
                           "register": register, "quotes": quotes},
                  "profile": profile, "symptoms": symptoms, "answer": answer,
                  **({"timeline": timeline} if timeline else {})}


# --- CP-ACS-006: heart attack in women -------------------------------------
add("P0077", "red", ["CP-ACS-006"], "terse adult",
    {"CP-ACS-006": [ACS6_LIST[0], ACS6_LIST[1], ACS6_LIST[2], ACS6_EITHER, ACS6_CALL]},
    prof(59, "female", ["high blood pressure"], ["amlodipine"]),
    "Ache between my shoulder blades for the last hour. Short of breath. Exhausted. No chest pain.",
    {"urgency": "red",
     "rationale": "An hour of pain between the shoulder blades with breathlessness and exhaustion in a "
                  "59-year-old woman, and no chest pain. The retrieved context says women more often have "
                  "pain in the shoulder, back or arm, shortness of breath and unusual tiredness, that "
                  "these can occur without any chest pain, and that they warrant calling 9-1-1.",
     "red_flags": ["Upper back pain for an hour, with breathlessness and exhaustion"],
     "next_steps": ["Call emergency services now", "Stop what you are doing and sit down while you wait"],
     "citations": ["CP-ACS-006"],
     "follow_up_questions": []},
    "T+0:00 ache between the shoulder blades began while shopping. T+0:40 short of breath, exhausted. "
    "T+1:00 unchanged.")

add("P0078", "red", ["CP-ACS-006", "CP-ACS-002"], "verbose and anxious",
    {"CP-ACS-006": [ACS6_LIST[2], ACS6_LIST[3], ACS6_EITHER, ACS6_CALL], "CP-ACS-002": [ACS2_SILENT]},
    prof(67, "female", ["type 2 diabetes"], ["metformin"]),
    "I do not want to make a fuss, but since lunch I have been feeling sick and strangely weak, and "
    "there is an ache going down my left arm. I keep telling myself it is something I ate, but it has "
    "not gone in three hours and I cannot settle.",
    {"urgency": "red",
     "rationale": "Three hours of left arm ache with weakness and an upset stomach in a 67-year-old woman "
                  "with diabetes. The retrieved context lists arm pain, unusual weakness and an upset "
                  "stomach among the symptoms women more often get, with or without chest pain, and says "
                  "to call 9-1-1. It also says heart attacks with mild or no symptoms are more common in "
                  "people with diabetes, which is why the absence of chest pain is not reassuring here.",
     "red_flags": ["Left arm ache with weakness for three hours, not settling"],
     "next_steps": ["Call emergency services now", "Do not drive yourself anywhere",
                    "Unlock the door and sit down where the crew can reach you"],
     "citations": ["CP-ACS-006", "CP-ACS-002"],
     "follow_up_questions": []},
    "T+0:00 feeling sick and weak after lunch. T+1:00 left arm ache began. T+3:00 unchanged.")

add("P0079", "red", ["CP-ACS-006", "CP-ACS-003"], "describing a third person",
    {"CP-ACS-006": [ACS6_LIST[0], ACS6_LIST[1], ACS6_LIST[4], ACS6_EITHER, ACS6_CALL],
     "CP-ACS-003": [ACS3_REST_SOB]},
    prof(62, "female"),
    "My wife suddenly went pale and clammy about half an hour ago. She says her jaw and her upper back "
    "ache and she cannot catch her breath sitting down. She is very anxious. She says there is no pain "
    "in her chest at all.",
    {"urgency": "red",
     "rationale": "Half an hour of jaw and upper back pain with breathlessness at rest, pallor, "
                  "clamminess and anxiety in a 62-year-old woman, without chest pain. The retrieved "
                  "context lists back, shoulder and arm pain, shortness of breath and anxiety among the "
                  "symptoms women more often have, says they can occur with no chest pain at all, and "
                  "says to call 9-1-1. Breathlessness at rest is listed for a heart attack.",
     "red_flags": ["Jaw and upper back pain for 30 minutes, with breathlessness at rest",
                   "Pale and clammy with the jaw and back pain"],
     "next_steps": ["Call emergency services now", "Stay with her and keep her sitting still",
                    "Do not drive her to hospital yourself"],
     "citations": ["CP-ACS-006", "CP-ACS-003"],
     "follow_up_questions": []},
    "T+0:00 pale, clammy, jaw and back ache began. T+0:20 breathless sitting down. T+0:30 unchanged.")

# --- CP-ANG-004: angina in women -------------------------------------------
add("P0080", "yellow", ["CP-ANG-004", "CP-ANG-005"], "plain and factual",
    {"CP-ANG-004": [ANG4_WOMEN, ANG4_OTHER], "CP-ANG-005": [ANG5_EXERTION, ANG5_REST, ANG5_PATTERN]},
    prof(61, "female", ["high blood pressure"], ["ramipril"]),
    "For about three months, when I walk briskly I get a heavy ache across my upper back and I feel "
    "light-headed and short of breath. It settles within a few minutes of slowing down.",
    {"urgency": "yellow",
     "rationale": "Three months of a consistent pattern: upper back ache with breathlessness and "
                  "light-headedness on brisk walking, relieved within minutes by slowing down. The "
                  "retrieved context says women more often feel angina pain in the back and more often "
                  "have breathlessness and light-headedness instead of chest pain, and gives pain on "
                  "exertion relieved by rest as the stable angina pattern. It has not been assessed.",
     "red_flags": ["Upper back ache with breathlessness on brisk walking, three months"],
     "next_steps": ["Arrange to be seen by your GP today and say you think this may be your heart",
                    "Call emergency services if an episode comes on at rest or does not settle when you stop"],
     "citations": ["CP-ANG-004", "CP-ANG-005"],
     "follow_up_questions": ["Is it happening after less walking than it used to?"]})

add("P0081", "yellow", ["CP-ANG-004", "CP-ANG-005"], "minimising the symptom",
    {"CP-ANG-004": [ANG4_WOMEN, ANG4_OTHER], "CP-ANG-005": [ANG5_EXERTION, ANG5_REST]},
    prof(55, "female"),
    "It is probably just being unfit, but when I carry the laundry upstairs my jaw and left arm ache "
    "and I feel a bit queasy. It goes off once I sit down for a couple of minutes. It has been like "
    "that since the spring.",
    {"urgency": "yellow",
     "rationale": "Jaw and left arm ache with queasiness brought on by climbing stairs and relieved by "
                  "sitting down, in the same pattern since spring. The retrieved context says women more "
                  "often feel angina in the jaw and arms and more often have nausea alongside, and gives "
                  "exertional pain relieved by rest as the stable angina pattern. Unfitness does not "
                  "explain a pattern that settles this reliably with rest.",
     "red_flags": ["Jaw and left arm ache on climbing stairs, eased by sitting down"],
     "next_steps": ["Book a GP appointment for today rather than waiting to see if it passes",
                    "Call emergency services if it comes on while you are resting or does not settle"],
     "citations": ["CP-ANG-004", "CP-ANG-005"],
     "follow_up_questions": ["Does it come on at a predictable point, like the same flight of stairs?"]})

add("P0082", "yellow", ["CP-ANG-004", "CP-ANG-005"], "describing a third person",
    {"CP-ANG-004": [ANG4_WOMEN, ANG4_OTHER], "CP-ANG-005": [ANG5_EXERTION, ANG5_REST, ANG5_5MIN]},
    prof(70, "female", ["high blood pressure"], ["amlodipine"]),
    "My mum gets a pain in both arms and goes short of breath when she walks the dog up the hill. It "
    "passes a couple of minutes after she stops. She has had it for a few months and has not mentioned "
    "it to anyone.",
    {"urgency": "yellow",
     "rationale": "A few months of arm pain with breathlessness brought on by walking uphill and passing "
                  "within minutes of stopping, in a 70-year-old woman. The retrieved context says women "
                  "more often feel angina in the arms and more often have breathlessness with it, and "
                  "gives exertional pain relieved by rest, going within five minutes, as the stable "
                  "pattern.",
     "red_flags": ["Pain in both arms with breathlessness on walking uphill, months"],
     "next_steps": ["Get her a GP appointment today and say it comes on with exertion",
                    "Call emergency services if an episode starts at rest or lasts more than a few minutes"],
     "citations": ["CP-ANG-004", "CP-ANG-005"],
     "follow_up_questions": ["Has she had to stop more often than she used to on that hill?"]})

add("P0083", "yellow", ["CP-ANG-004", "CP-ANG-003"], "poor spelling and punctuation",
    {"CP-ANG-004": [ANG4_WOMEN, ANG4_OTHER], "CP-ANG-003": [ANG3_SPREAD, ANG3_INDIGESTION]},
    prof(64, "female", ["high cholesterol"], ["atorvastatin"]),
    "gettin a achin in my neck n jaw wen i hoover upstairs, feels a bit like indigestion, n im out of "
    "breath wiv it. goes off wen i stop. been happenin few months now",
    {"urgency": "yellow",
     "rationale": "Months of neck and jaw ache with breathlessness on housework, described as feeling "
                  "like indigestion and relieved by stopping. The retrieved context says angina "
                  "discomfort is often felt in the neck and jaw, that it can feel like heartburn or "
                  "indigestion, and that women more often get it in those places with breathlessness "
                  "alongside.",
     "red_flags": ["Neck and jaw ache with breathlessness on housework, eased by stopping"],
     "next_steps": ["Ask your GP for an appointment today and mention it comes on with effort",
                    "Call emergency services if it comes on while you are sitting or does not go away"],
     "citations": ["CP-ANG-004", "CP-ANG-003"],
     "follow_up_questions": ["Does anything else bring it on, like cold weather or stress?"]})

# --- CP-ANG-005 and CP-ANG-009: stable angina as thresholds ----------------
add("P0084", "yellow", ["CP-ANG-005", "CP-ANG-009"], "verbose and anxious",
    {"CP-ANG-005": [ANG5_EXERTION, ANG5_REST, ANG5_5MIN, ANG5_PATTERN], "CP-ANG-009": [ANG9_STABLE]},
    prof(68, "male", ["coronary artery disease", "stable angina"], ["atorvastatin", "bisoprolol"]),
    "I know my angina well by now, and this was the same as always: it came on carrying the shopping in "
    "from the car, I sat down, and it had gone in two or three minutes. Nothing has changed about it in "
    "the year I have had it. I am only asking because my wife told me to.",
    {"urgency": "yellow",
     "rationale": "A known angina episode that behaved exactly as usual: brought on by carrying shopping, "
                  "gone in two or three minutes of sitting, with an unchanged pattern for a year. Every "
                  "stable criterion in the retrieved context is met and none of the unstable ones. "
                  "Angina still means a review rather than self-care.",
     "red_flags": ["Exertional chest pain in known angina, settling within minutes"],
     "next_steps": ["Arrange to be seen by your GP or heart team today",
                    "Call emergency services if an episode lasts longer, comes on at rest, or does not "
                    "settle when you stop"],
     "citations": ["CP-ANG-005", "CP-ANG-009"],
     "follow_up_questions": ["Are you having them more often than a year ago?"]},
    "T+0:00 tightness began carrying shopping. T+0:01 sat down. T+0:03 gone.")

add("P0085", "yellow", ["CP-ANG-005", "CP-ANG-009"], "poor spelling and punctuation",
    {"CP-ANG-005": [ANG5_EXERTION, ANG5_REST, ANG5_5MIN], "CP-ANG-009": [ANG9_STABLE]},
    prof(74, "male", ["angina"], ["isosorbide mononitrate"]),
    "chest went tight walkin to the post box like it does. stoped n it went in 4 or 5 mins. same as "
    "always for 2 yrs",
    {"urgency": "yellow",
     "rationale": "Known angina brought on by walking and gone within five minutes of stopping, "
                  "unchanged for two years. That is the stable pattern the retrieved context describes, "
                  "and it says a person with stable angina can predict when an event will occur. A review "
                  "is still warranted.",
     "red_flags": ["Chest tightness on walking in known angina, gone within five minutes"],
     "next_steps": ["Ask your GP for a review appointment today",
                    "Call emergency services if one lasts more than twenty minutes or starts at rest"],
     "citations": ["CP-ANG-005", "CP-ANG-009"],
     "follow_up_questions": ["Has the distance you can walk before it starts got shorter?"]})

# --- CP-ANG-007 and 011: microvascular angina ------------------------------
add("P0086", "red", ["CP-ANG-007", "CP-ANG-011", "CP-ANG-006"], "verbose and anxious",
    {"CP-ANG-007": ANG7_LIST, "CP-ANG-011": [ANG11_MICRO], "CP-ANG-006": [ANG6_INTENSE, ANG6_REST]},
    prof(58, "female", ["angina"], ["amlodipine"]),
    "I have had angina for a while, but this is not like it. An intense pain came across my chest while "
    "I was sitting watching television an hour ago, and it is still going, and I am short of breath "
    "with it. I have been lying still and it has not eased at all.",
    {"urgency": "red",
     "rationale": "An hour of intense chest pain that began at rest, has not eased with lying still, and "
                  "comes with breathlessness. The retrieved context lists intense pain, pain lasting a "
                  "long time, pain at rest and shortness of breath together, says events of this type can "
                  "be unstable and can last longer than other angina, and lists intense pain and pain at "
                  "rest among the unstable features.",
     "red_flags": ["Intense chest pain at rest for an hour, not easing",
                   "Short of breath with the chest pain at rest"],
     "next_steps": ["Call emergency services now", "Do not drive yourself to hospital",
                    "Stay sitting or lying still until help arrives"],
     "citations": ["CP-ANG-007", "CP-ANG-011", "CP-ANG-006"],
     "follow_up_questions": []},
    "T+0:00 intense chest pain began sitting watching television. T+0:30 lying still, no easing. "
    "T+1:00 unchanged, short of breath.")

# --- CP-ANG-008 and 012: vasospastic angina --------------------------------
add("P0087", "red", ["CP-ANG-008", "CP-ANG-012"], "plain and factual",
    {"CP-ANG-008": ANG8_LIST, "CP-ANG-012": [ANG12_SPASM]},
    prof(48, "male"),
    "For the last three nights I have been woken around four in the morning by a tight, heavy pain in "
    "my chest that lasts about a quarter of an hour and then goes. During the day I am fine, even at "
    "the gym.",
    {"urgency": "red",
     "rationale": "Three nights of chest pain waking him in the early hours, at rest, lasting about "
                  "fifteen minutes, with no symptoms on exertion. The retrieved context describes angina "
                  "that starts at night or in the early morning hours at rest, in a pattern, lasting "
                  "around fifteen minutes, and says it is caused by a spasm that can block blood flow to "
                  "the heart and cause serious pain. Pain at rest is not a stable pattern, whatever the "
                  "cause, and needs emergency assessment rather than an appointment.",
     "red_flags": ["Chest pain waking him at rest, three nights running",
                   "Each episode lasting about fifteen minutes"],
     "next_steps": ["Go to an emergency department now rather than waiting for an appointment",
                    "Call emergency services if the pain comes back or lasts longer than before",
                    "Do not drive yourself"],
     "citations": ["CP-ANG-008", "CP-ANG-012"],
     "follow_up_questions": []},
    "T+0:00 woken at 04:00 by chest pain, three nights running. T+0:15 each episode gone. "
    "T+24:00 no symptoms during the day, including at the gym.")

# --- CP-ANG-006 and 010: unstable angina ----------------------------------
add("P0088", "red", ["CP-ANG-006", "CP-ANG-010"], "plain and factual",
    {"CP-ANG-006": [ANG6_20MIN, ANG6_NOTRELIEVED], "CP-ANG-010": [ANG10_EMERGENCY, ANG10_NOPATTERN]},
    prof(64, "male", ["coronary artery disease", "angina"], ["aspirin", "atorvastatin"]),
    "My angina has been coming on with less and less effort this week. Today it started just walking to "
    "the kitchen and it has lasted twenty-five minutes, even though I sat straight down.",
    {"urgency": "red",
     "rationale": "Angina that has lasted twenty-five minutes and did not settle on sitting down, after a "
                  "week of coming on with less effort. The retrieved context lists pain lasting longer "
                  "than twenty minutes and pain not relieved by rest among the unstable features, says "
                  "unstable angina may occur more often and be more painful than stable angina, and "
                  "calls it a medical emergency.",
     "red_flags": ["Angina lasting twenty-five minutes despite sitting down",
                   "Coming on with less effort through this week"],
     "next_steps": ["Call emergency services now", "Do not drive yourself to hospital",
                    "Sit down and stay still until the ambulance arrives"],
     "citations": ["CP-ANG-006", "CP-ANG-010"],
     "follow_up_questions": []},
    "T+0:00 tightness began walking to the kitchen. T+0:01 sat down. T+0:25 unchanged.")

add("P0089", "red", ["CP-ANG-006", "CP-ANG-010"], "minimising the symptom",
    {"CP-ANG-006": [ANG6_REST, ANG6_20MIN], "CP-ANG-010": [ANG10_EMERGENCY, ANG10_NOPATTERN]},
    prof(69, "female", ["angina"], ["bisoprolol"]),
    "It is my usual chest thing, probably nothing, but it woke me up last night and it has come back "
    "twice today while I was just sitting.",
    {"urgency": "red",
     "rationale": "Angina that woke her from sleep and has returned twice at rest in one day. The "
                  "retrieved context lists pain during rest or sleep, and pain that goes away and comes "
                  "back, among the unstable features, says unstable angina does not follow a pattern and "
                  "may occur more often, and calls it a medical emergency. That each episode passed does "
                  "not make it her usual pattern.",
     "red_flags": ["Angina waking her from sleep at night",
                   "Two further episodes today while sitting at rest"],
     "next_steps": ["Call emergency services now", "Do not wait to see whether the next one passes",
                    "Sit down and stay where you are"],
     "citations": ["CP-ANG-006", "CP-ANG-010"],
     "follow_up_questions": []},
    "T+0:00 woken from sleep by chest pain last night. T+14:00 episode while sitting. "
    "T+20:00 second episode while sitting.")

# --- CP-ANG-003: the angina symptom list ----------------------------------
add("P0090", "yellow", ["CP-ANG-003", "CP-ANG-005"], "plain and factual",
    {"CP-ANG-003": [ANG3_SPREAD], "CP-ANG-005": [ANG5_EXERTION, ANG5_REST, ANG5_PATTERN]},
    prof(60, "male"),
    "When I walk the dog up the hill I get a heavy, pressing feeling behind my breastbone that spreads "
    "into my left shoulder. It goes after a few minutes of standing still. It started about three "
    "months ago and has not changed since.",
    {"urgency": "yellow",
     "rationale": "Three months of an unchanged pattern: heavy pressure behind the breastbone spreading "
                  "to the left shoulder on walking uphill, relieved within minutes by standing still. The "
                  "retrieved context says angina discomfort spreads to areas such as the shoulders and "
                  "gives exertional pain relieved by rest, unchanged over two months, as the stable "
                  "pattern. Never assessed, so it needs seeing.",
     "red_flags": ["Pressure behind the breastbone spreading to the shoulder on exertion"],
     "next_steps": ["Arrange to be seen by your GP today",
                    "Call emergency services if it comes on at rest or does not go when you stop"],
     "citations": ["CP-ANG-003", "CP-ANG-005"],
     "follow_up_questions": ["Does it come on at the same point on the hill each time?"]})

add("P0091", "red", ["CP-ANG-003"], "panicked caregiver",
    {"CP-ANG-003": [ANG3_CALL, ANG3_SPREAD]},
    prof(58, "male", ["high blood pressure"], ["amlodipine"]),
    "My husband has heavy pressure behind his breastbone going up into his jaw! It came on walking home, "
    "he has been sitting down for twenty minutes and it is no better! What do I do?",
    {"urgency": "red",
     "rationale": "Heavy pressure behind the breastbone spreading to the jaw, unchanged after twenty "
                  "minutes of sitting down. The retrieved context says to call 9-1-1 for chest discomfort "
                  "that does not go away with rest, and describes discomfort spreading to the jaw.",
     "red_flags": ["Pressure behind the breastbone into the jaw, unchanged after twenty minutes"],
     "next_steps": ["Call emergency services now", "Do not drive him to hospital yourself",
                    "Keep him sitting down and stay with him"],
     "citations": ["CP-ANG-003"],
     "follow_up_questions": []},
    "T+0:00 pressure began walking home. T+0:02 sat down. T+0:20 unchanged.")

# --- CP-PNA-002: what raises pneumonia risk -------------------------------
add("P0092", "yellow", ["CP-PNA-001", "CP-PNA-002"], "terse adult",
    {"CP-PNA-001": PNA1_LIST, "CP-PNA-002": [PNA2_LUNG]},
    prof(67, "male", ["COPD"], ["tiotropium inhaler"]),
    "COPD here. Three days worse. Coughing up thick green stuff, fever, chest hurts when I cough. "
    "Breathing about my usual.",
    {"urgency": "yellow",
     "rationale": "Three days of fever with thick green sputum and chest pain on coughing. The retrieved "
                  "context lists those among the symptoms of pneumonia and names COPD among the lung "
                  "diseases that increase pneumonia risk. Breathing is at his usual baseline rather than "
                  "worse, so this is assessment today rather than emergency care.",
     "red_flags": ["Three days of fever with green sputum and chest pain on coughing"],
     "next_steps": ["Be seen by your GP or respiratory team today",
                    "Call emergency services if your breathing becomes worse than your usual, or you "
                    "become confused or drowsy"],
     "citations": ["CP-PNA-001", "CP-PNA-002"],
     "follow_up_questions": ["Is your breathing worse than your usual day-to-day?"]},
    "T+0:00 cough and fever began three days ago. T+72:00 sputum thick and green, chest pain on coughing.")

add("P0093", "yellow", ["CP-PNA-001", "CP-PNA-002"], "verbose and anxious",
    {"CP-PNA-001": PNA1_LIST, "CP-PNA-002": [PNA2_STEROID]},
    prof(45, "female", ["rheumatoid arthritis"], ["prednisolone"]),
    "I am on steroid tablets for my arthritis, and over the last two days I have come down with a fever "
    "and a cough bringing up yellow phlegm. My chest is sore when I cough. I read that steroids make "
    "infections worse and now I am frightened.",
    {"urgency": "yellow",
     "rationale": "Two days of fever with a productive cough and chest pain on coughing, while taking "
                  "long-term steroids. The retrieved context lists those symptoms for pneumonia and says "
                  "long-term use of steroid medicines weakens the immune system, which is why this needs "
                  "assessing today rather than waiting.",
     "red_flags": ["Two days of fever with yellow phlegm and chest pain on coughing"],
     "next_steps": ["Contact your GP today and say you are on long-term steroids",
                    "Call emergency services if you become short of breath at rest or confused"],
     "citations": ["CP-PNA-001", "CP-PNA-002"],
     "follow_up_questions": ["Have you been told what to do about your steroid dose when you are unwell?"]},
    "T+0:00 fever and cough began two days ago. T+48:00 yellow phlegm, chest sore on coughing.")

add("P0094", "yellow", ["CP-PNA-001", "CP-PNA-002"], "describing a third person",
    {"CP-PNA-001": PNA1_LIST + [PNA1_RISK], "CP-PNA-002": [PNA2_OTHER]},
    prof(72, "male", ["heart failure", "type 2 diabetes"], ["furosemide", "metformin"]),
    "My husband has had a cough and a fever since Tuesday and he has gone off his food. His chest aches "
    "when he coughs. He is breathing the same as usual and he is his normal self otherwise.",
    {"urgency": "yellow",
     "rationale": "Several days of cough and fever with chest pain on coughing and loss of appetite in a "
                  "72-year-old with heart failure and diabetes. The retrieved context lists those "
                  "symptoms for pneumonia, names heart failure and diabetes as additional risk factors, "
                  "and says older adults and people with serious health conditions are at risk of more "
                  "serious pneumonia. He is alert and breathing normally, so this is same-day assessment.",
     "red_flags": ["Cough and fever since Tuesday with chest pain on coughing"],
     "next_steps": ["Get him a GP appointment today and mention the heart failure",
                    "Call emergency services if he becomes short of breath at rest, confused or drowsy"],
     "citations": ["CP-PNA-001", "CP-PNA-002"],
     "follow_up_questions": ["Has he been more short of breath than usual when lying flat?"]})

# --- CP-PNA-003: the cold that outlasts a cold ----------------------------
add("P0095", "yellow", ["CP-PNA-003", "CP-PNA-001"], "poor spelling and punctuation",
    {"CP-PNA-003": [PNA3_COLD], "CP-PNA-001": PNA1_LIST},
    prof(33, "female"),
    "had a cold for nearly 2 weeks n its getting worse not better, now iv got a fever n my chest hurts "
    "when i cough",
    {"urgency": "yellow",
     "rationale": "A cold-like illness now in its second week, getting worse rather than better, with a "
                  "new fever and chest pain on coughing. The retrieved context says pneumonia can look "
                  "the same as a cold and that you may not realise it is more serious until it lasts "
                  "longer than a cold would, and it lists fever and chest pain on coughing among the "
                  "symptoms.",
     "red_flags": ["Cold worsening into a second week, now with fever",
                   "Chest pain on coughing, new this week"],
     "next_steps": ["Be seen by your GP today rather than waiting it out",
                    "Call emergency services if you become short of breath at rest"],
     "citations": ["CP-PNA-003", "CP-PNA-001"],
     "follow_up_questions": ["Are you bringing up any phlegm, and what colour is it?"]},
    "T+0:00 cold symptoms began twelve days ago. T+240:00 worse rather than better. "
    "T+264:00 fever and chest pain on coughing.")
