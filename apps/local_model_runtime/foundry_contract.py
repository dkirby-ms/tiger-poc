from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DeploymentContract:
    model_id: str
    route: str
    secret: str
    ready: bool = True


class LocalFoundryDeploymentRuntime:
    """Deterministic Foundry Local contract harness for local validation."""

    def __init__(self):
        self.deployment_contracts = [
            DeploymentContract(model_id="yolo", route="/v1/predict", secret="yolo-secret", ready=True),
            DeploymentContract(model_id="florence-2", route="/v1/predict", secret="florence-2-secret", ready=True),
            DeploymentContract(model_id="phi-4-multimodal", route="/v1/chat/completions", secret="phi-4-multimodal-secret", ready=True),
        ]
        self._ready_override = {contract.model_id: contract.ready for contract in self.deployment_contracts}

    def set_ready(self, model_id: str, ready: bool) -> None:
        if model_id not in self._ready_override:
            raise KeyError(f"Unknown model deployment: {model_id}")
        self._ready_override[model_id] = ready

    def _get_contract(self, model_id: str):
        for contract in self.deployment_contracts:
            if contract.model_id == model_id:
                return contract
        return None

    def _route_valid(self, contract: DeploymentContract, route: str) -> bool:
        return contract.route == route

    def _payload_valid(self, contract: DeploymentContract, payload: dict) -> bool:
        if contract.route == "/v1/predict":
            return "image" in payload and "messages" not in payload
        if contract.route == "/v1/chat/completions":
            return "messages" in payload and "image" not in payload
        return False

    def dispatch(self, model_id: str, route: str, secret: str, payload: dict):
        contract = self._get_contract(model_id)
        if contract is None:
            return {"status": "unknown_model", "model_id": model_id, "route": route}

        if not self._ready_override.get(model_id, contract.ready):
            return {
                "status": "not_ready",
                "model_id": contract.model_id,
                "route": contract.route,
                "receipt": "deployment-not-ready",
            }

        if not self._route_valid(contract, route):
            return {
                "status": "wrong_route",
                "model_id": contract.model_id,
                "expected_route": contract.route,
                "received_route": route,
            }

        if secret != contract.secret:
            return {
                "status": "unauthorized",
                "model_id": contract.model_id,
                "route": contract.route,
                "expected_secret": contract.secret,
            }

        if not self._payload_valid(contract, payload):
            return {
                "status": "wrong_payload",
                "model_id": contract.model_id,
                "route": contract.route,
                "expected_payload": "predictive" if contract.route == "/v1/predict" else "chat-completion",
            }

        return {
            "status": "ok",
            "model_id": contract.model_id,
            "route": contract.route,
            "secret": secret,
            "payload_type": "predictive" if contract.route == "/v1/predict" else "chat-completion",
        }
