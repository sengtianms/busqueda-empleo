from shared.errors import InternalError
from shared.models import OfferState

VALID_TRANSITIONS: dict[OfferState, list[OfferState]] = {
    OfferState.DESCUBIERTA: [OfferState.PREPARADA],
    OfferState.PREPARADA: [OfferState.EVALUADA, OfferState.DUPLICADA],
    OfferState.EVALUADA: [
        OfferState.ACEPTADA_EI,
        OfferState.DESCARTADA_EI,
        OfferState.ACEPTADA,
        OfferState.DESCARTADA,
    ],
    OfferState.ACEPTADA: [OfferState.PROCESADA],
    OfferState.DESCARTADA: [OfferState.FINALIZADA],
    OfferState.PROCESADA: [OfferState.FINALIZADA],
}


def transition(
    current_state: OfferState,
    target_state: OfferState,
) -> OfferState:
    if (
        current_state in VALID_TRANSITIONS
        and target_state in VALID_TRANSITIONS[current_state]
    ):
        return target_state
    raise InternalError(
        "010",
        f"Invalid transition: {current_state.value} -> {target_state.value}",
        source_module="state_machine",
    )


def possible_transitions(state: OfferState) -> list[OfferState]:
    return VALID_TRANSITIONS.get(state, [])
