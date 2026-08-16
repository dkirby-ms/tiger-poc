"""Deployment registry for managing deployment lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from .foundry_contract import DeploymentConfig, DeploymentContract, DeploymentState


class DeploymentRegistry:
    """Manages deployment lifecycle and state."""

    def __init__(self):
        """Initialize the registry."""
        self._deployments: Dict[str, DeploymentContract] = {}

    def create_deployment(self, config: DeploymentConfig) -> DeploymentContract:
        """
        Create a new deployment from configuration.
        
        Args:
            config: DeploymentConfig with model_id, route, and secret
            
        Returns:
            Created DeploymentContract
            
        Raises:
            ValueError: If model_id already exists or config is invalid
        """
        config.validate()
        
        if config.model_id in self._deployments:
            raise ValueError(f"Deployment with model_id '{config.model_id}' already exists")
        
        # Check for duplicate secrets
        for existing in self._deployments.values():
            if existing.secret == config.secret and existing.status != DeploymentState.TERMINATING:
                raise ValueError(f"Secret already in use by deployment '{existing.model_id}'")
        
        now = datetime.now(timezone.utc)
        contract = DeploymentContract(
            model_id=config.model_id,
            route=config.route,
            secret=config.secret,
            ready=True,
            status=DeploymentState.RUNNING,
            created_at=now,
            updated_at=now,
            workload_type=config.resolved_workload_type,
        )
        
        self._deployments[config.model_id] = contract
        return contract

    def get_deployment(self, model_id: str) -> Optional[DeploymentContract]:
        """
        Get deployment by model_id.
        
        Args:
            model_id: The model identifier
            
        Returns:
            DeploymentContract or None if not found
        """
        contract = self._deployments.get(model_id)
        if contract and contract.status == DeploymentState.TERMINATING:
            return None
        return contract

    def list_deployments(self) -> List[DeploymentContract]:
        """
        List all active deployments.
        
        Returns:
            List of active DeploymentContracts (excludes deleted)
        """
        return [
            contract
            for contract in self._deployments.values()
            if contract.status != DeploymentState.TERMINATING
        ]

    def delete_deployment(self, model_id: str) -> bool:
        """
        Delete a deployment by model_id.
        
        Args:
            model_id: The model identifier
            
        Returns:
            True if deleted, False if not found
        """
        if model_id not in self._deployments:
            return False
        
        contract = self._deployments[model_id]
        if contract.status == DeploymentState.TERMINATING:
            return False
        
        # Mark as deleted - don't remove to preserve history
        now = datetime.now(timezone.utc)
        deleted_contract = DeploymentContract(
            model_id=contract.model_id,
            route=contract.route,
            secret=contract.secret,
            ready=False,
            status=DeploymentState.TERMINATING,
            created_at=contract.created_at,
            updated_at=now,
            workload_type=contract.workload_type,
        )
        
        self._deployments[model_id] = deleted_contract
        return True

    def set_ready(self, model_id: str, ready: bool) -> None:
        """
        Set deployment ready status.
        
        Args:
            model_id: The model identifier
            ready: Ready status
            
        Raises:
            KeyError: If deployment not found
        """
        if model_id not in self._deployments:
            raise KeyError(f"Unknown model deployment: {model_id}")
        
        contract = self._deployments[model_id]
        if contract.status == DeploymentState.TERMINATING:
            raise KeyError(f"Cannot modify deleted deployment: {model_id}")
        
        # Create updated contract with new ready status
        now = datetime.now(timezone.utc)
        updated_contract = DeploymentContract(
            model_id=contract.model_id,
            route=contract.route,
            secret=contract.secret,
            ready=ready,
            status=contract.status,
            created_at=contract.created_at,
            updated_at=now,
            workload_type=contract.workload_type,
        )
        
        self._deployments[model_id] = updated_contract

    def get_status(self, model_id: str) -> Optional[DeploymentState]:
        """
        Get deployment status.
        
        Args:
            model_id: The model identifier
            
        Returns:
            DeploymentState or None if not found
        """
        contract = self.get_deployment(model_id)
        return contract.status if contract else None

    def is_ready(self, model_id: str) -> bool:
        """
        Check if deployment is ready.
        
        Args:
            model_id: The model identifier
            
        Returns:
            True if ready and not deleted, False otherwise
        """
        contract = self.get_deployment(model_id)
        return contract is not None and contract.ready and contract.status == DeploymentState.RUNNING
