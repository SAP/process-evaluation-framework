"""
Edge-case minimal-JSON fixtures for testing calculate_bpmn_similarity
and the dashboard's None-propagation behavior.

Paste any pair into a notebook cell and run:

    from bpmn_similarity import calculate_bpmn_similarity
    result = calculate_bpmn_similarity(MODEL_A, MODEL_B, method="dice")
    print("overall:", result["overall"])
    print("high_level_scores:", result["high_level_scores"])
    print("data_presence:", result["data_presence"])

To see how the dashboard handles each fixture, launch the marimo
dashboard and load a pair via its file picker:

    poetry run marimo edit notebooks/dashboard.py
"""

# =============================================================================
# FIXTURE 1 — Identical minimal pair (no flows, no gateways, no pools, no subprocess).
# Tests: which grouped scores are None when most categories are empty-vs-empty.
# Expected:
#   - "elements" grouped: defined (both have activities + events)
#   - "flows" grouped: None (no seq flows on either side -> by rule 4)
#   - "organizational" grouped: None (no pools/lanes on either side)
#   - "subprocess" grouped: None (no subprocesses)
#   - overall: defined, equals elements score
#   - Dashboard: three sliders disabled (flows, organizational, subprocess);
#                three "N/A" rows in left chart; only elements slider active.
# =============================================================================

FIXTURE_1_A = {
    "activities": [
        {"id": "a1", "name": "Receive order", "type": "Task"},
        {"id": "a2", "name": "Ship product", "type": "Task"},
    ],
    "events": [
        {"id": "e1", "name": "Start", "type": "StartNoneEvent"},
        {"id": "e2", "name": "End", "type": "EndNoneEvent"},
    ],
    "gateways": [],
    "sequenceFlows": [],
    "messageFlows": [],
    "pools": [],
}

FIXTURE_1_B = {
    "activities": [
        {"id": "a1", "name": "Receive order", "type": "Task"},
        {"id": "a2", "name": "Ship product", "type": "Task"},
    ],
    "events": [
        {"id": "e1", "name": "Start", "type": "StartNoneEvent"},
        {"id": "e2", "name": "End", "type": "EndNoneEvent"},
    ],
    "gateways": [],
    "sequenceFlows": [],
    "messageFlows": [],
    "pools": [],
}


# =============================================================================
# FIXTURE 2 — Both models have seq flows but no msg flows.
# Tests: adaptive flow weighting (Option B) — msg flows empty in both, so flows
# grouped = seq score only, NOT 70/30 averaged with bogus 1.0.
# Expected:
#   - data_presence["mes_flows_str"] = False
#   - data_presence["seq_flows_str"] = True
#   - "flows" grouped = seq_flows_str score (not (seq + 1.0) / 2)
#   - Dashboard: Msg Flows row in right chart is gray "no data"; flow slider
#     remains active.
# =============================================================================

FIXTURE_2_A = {
    "activities": [
        {"id": "a1", "name": "Receive order", "type": "Task"},
        {"id": "a2", "name": "Ship product", "type": "Task"},
    ],
    "events": [
        {"id": "e1", "name": "Start", "type": "StartNoneEvent"},
        {"id": "e2", "name": "End", "type": "EndNoneEvent"},
    ],
    "gateways": [],
    "sequenceFlows": [
        {"id": "f1", "sourceRef": "e1", "targetRef": "a1"},
        {"id": "f2", "sourceRef": "a1", "targetRef": "a2"},
        {"id": "f3", "sourceRef": "a2", "targetRef": "e2"},
    ],
    "messageFlows": [],
    "pools": [],
}

FIXTURE_2_B = {
    "activities": [
        {"id": "a1", "name": "Receive order", "type": "Task"},
        {"id": "a2", "name": "Send confirmation", "type": "Task"},  # differs from A
    ],
    "events": [
        {"id": "e1", "name": "Start", "type": "StartNoneEvent"},
        {"id": "e2", "name": "End", "type": "EndNoneEvent"},
    ],
    "gateways": [],
    "sequenceFlows": [
        {"id": "f1", "sourceRef": "e1", "targetRef": "a1"},
        {"id": "f2", "sourceRef": "a1", "targetRef": "a2"},
        {"id": "f3", "sourceRef": "a2", "targetRef": "e2"},
    ],
    "messageFlows": [],
    "pools": [],
}


# =============================================================================
# FIXTURE 3 — Neither model has activities. Only events, gateways, flows.
# Tests: "elements" adaptive — activities sub-bucket is empty-vs-empty, but
# events and gateways still contribute. Elements grouped should average over
# events+gateways only, NOT three with a bogus 1.0 for activities.
# Expected:
#   - data_presence["activity_names"] = False, data_presence["activity_types"] = False
#   - high_level_scores["elements"] = (events + gateways) / 2, NOT
#     (1.0 + events + gateways) / 3
#   - Dashboard: in the left chart, elements still appears; in the right chart,
#     "Activities" row is grayed out as "no data".
# =============================================================================

FIXTURE_3_A = {
    "activities": [],
    "events": [
        {"id": "e1", "name": "Start", "type": "StartNoneEvent"},
        {"id": "e2", "name": "End", "type": "EndNoneEvent"},
    ],
    "gateways": [
        {"id": "g1", "name": "Decision", "type": "Exclusive"},
    ],
    "sequenceFlows": [
        {"id": "f1", "sourceRef": "e1", "targetRef": "g1"},
        {"id": "f2", "sourceRef": "g1", "targetRef": "e2"},
    ],
    "messageFlows": [],
    "pools": [],
}

FIXTURE_3_B = {
    "activities": [],
    "events": [
        {"id": "e1", "name": "Start", "type": "StartNoneEvent"},
        {"id": "e2", "name": "End", "type": "EndNoneEvent"},
    ],
    "gateways": [
        {"id": "g1", "name": "Choice", "type": "Exclusive"},  # name differs
    ],
    "sequenceFlows": [
        {"id": "f1", "sourceRef": "e1", "targetRef": "g1"},
        {"id": "f2", "sourceRef": "g1", "targetRef": "e2"},
    ],
    "messageFlows": [],
    "pools": [],
}


# =============================================================================
# FIXTURE 4 — Both models truly empty.
# Tests: extreme edge case — every grouped score should be None, overall None.
# Expected:
#   - All data_presence values: False
#   - All high_level_scores values: None
#   - overall: None
#   - Dashboard: all four sliders disabled; watermark "N/A"; all four rows
#     grayed out in left chart. Behavioral compute would also yield None
#     (no traces possible).
# =============================================================================

FIXTURE_4_A = {
    "activities": [],
    "events": [],
    "gateways": [],
    "sequenceFlows": [],
    "messageFlows": [],
    "pools": [],
}

FIXTURE_4_B = {
    "activities": [],
    "events": [],
    "gateways": [],
    "sequenceFlows": [],
    "messageFlows": [],
    "pools": [],
}


# =============================================================================
# FIXTURE 5 — Subprocess with mix of present/empty sub-keys.
# Tests: subprocess inner-formula rescaling. Both have an unnamed subprocess
# (so subprocess_names is empty-vs-empty per data_presence) but with content
# (elemRefs and flows present). Inner formula should rescale 0.3/0.5 weights to
# sum to 1 (since 0.2 for names is dropped), giving 0.375 / 0.625.
# Expected:
#   - data_presence["subprocess_names"] = False
#   - data_presence["subprocess_elemrefs"] = True
#   - data_presence["subprocess_flows"] = True
#   - subprocess grouped = (0.3/0.8) * elemrefs + (0.5/0.8) * flows
#                       = 0.375 * elemrefs + 0.625 * flows
# =============================================================================

FIXTURE_5_A = {
    "activities": [
        {"id": "sp1", "name": "", "type": "Subprocess",
         "elemRefs": ["sa1", "sa2"],
         "subprocessSequenceFlows": [
             {"id": "sf1", "sourceRef": "sa1", "targetRef": "sa2"}
         ]},
        {"id": "sa1", "name": "Validate request", "type": "Task",
         "parent_subprocess": "sp1"},
        {"id": "sa2", "name": "Send response", "type": "Task",
         "parent_subprocess": "sp1"},
        {"id": "a_top", "name": "Receive request", "type": "Task"},
    ],
    "events": [
        {"id": "e1", "name": "Start", "type": "StartNoneEvent"},
        {"id": "e2", "name": "End", "type": "EndNoneEvent"},
    ],
    "gateways": [],
    "sequenceFlows": [
        {"id": "f1", "sourceRef": "e1", "targetRef": "a_top"},
        {"id": "f2", "sourceRef": "a_top", "targetRef": "sp1"},
        {"id": "f3", "sourceRef": "sp1", "targetRef": "e2"},
    ],
    "messageFlows": [],
    "pools": [],
}

FIXTURE_5_B = {
    "activities": [
        {"id": "sp1", "name": "", "type": "Subprocess",
         "elemRefs": ["sa1", "sa2"],
         "subprocessSequenceFlows": [
             {"id": "sf1", "sourceRef": "sa1", "targetRef": "sa2"}
         ]},
        {"id": "sa1", "name": "Validate request", "type": "Task",
         "parent_subprocess": "sp1"},
        {"id": "sa2", "name": "Send response", "type": "Task",
         "parent_subprocess": "sp1"},
        {"id": "a_top", "name": "Receive request", "type": "Task"},
    ],
    "events": [
        {"id": "e1", "name": "Start", "type": "StartNoneEvent"},
        {"id": "e2", "name": "End", "type": "EndNoneEvent"},
    ],
    "gateways": [],
    "sequenceFlows": [
        {"id": "f1", "sourceRef": "e1", "targetRef": "a_top"},
        {"id": "f2", "sourceRef": "a_top", "targetRef": "sp1"},
        {"id": "f3", "sourceRef": "sp1", "targetRef": "e2"},
    ],
    "messageFlows": [],
    "pools": [],
}


# =============================================================================
# FIXTURE 6 — Pools/lanes in both, no subprocess, no msg flows.
# Tests: combination — flows uses seq-only adaptive, organizational defined,
# subprocess None, elements defined.
# Expected:
#   - high_level_scores: elements defined, flows defined, organizational
#     defined, subprocess = None
#   - Dashboard: subprocess slider disabled; other three active.
# =============================================================================

FIXTURE_6_A = {
    "activities": [
        {"id": "a1", "name": "Process order", "type": "Task"},
    ],
    "events": [
        {"id": "e1", "name": "Start", "type": "StartNoneEvent"},
        {"id": "e2", "name": "End", "type": "EndNoneEvent"},
    ],
    "gateways": [],
    "sequenceFlows": [
        {"id": "f1", "sourceRef": "e1", "targetRef": "a1"},
        {"id": "f2", "sourceRef": "a1", "targetRef": "e2"},
    ],
    "messageFlows": [],
    "pools": [
        {"id": "p1", "name": "Sales",
         "lanes": [
             {"id": "l1", "name": "Agent", "elemRefs": ["a1", "e1", "e2"]},
         ]},
    ],
}

FIXTURE_6_B = {
    "activities": [
        {"id": "a1", "name": "Process order", "type": "Task"},
    ],
    "events": [
        {"id": "e1", "name": "Start", "type": "StartNoneEvent"},
        {"id": "e2", "name": "End", "type": "EndNoneEvent"},
    ],
    "gateways": [],
    "sequenceFlows": [
        {"id": "f1", "sourceRef": "e1", "targetRef": "a1"},
        {"id": "f2", "sourceRef": "a1", "targetRef": "e2"},
    ],
    "messageFlows": [],
    "pools": [
        {"id": "p1", "name": "Customer service",  # pool name differs
         "lanes": [
             {"id": "l1", "name": "Rep", "elemRefs": ["a1", "e1", "e2"]},
         ]},
    ],
}