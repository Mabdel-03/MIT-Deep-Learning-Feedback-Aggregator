"""
Piazza authentication module.
"""
from piazza_api import Piazza
from rich.console import Console

console = Console()


class PiazzaAuth:
    """Handles Piazza authentication and network access."""
    
    def __init__(self, email: str, password: str):
        """
        Initialize Piazza authentication.
        
        Args:
            email: Piazza account email
            password: Piazza account password
        """
        self.email = email
        self.password = password
        self.piazza = Piazza()
        self._authenticated = False
    
    def login(self) -> bool:
        """
        Authenticate with Piazza.
        
        Returns:
            True if authentication successful, False otherwise
        """
        try:
            console.print(f"[yellow]Logging in as {self.email}...[/yellow]")
            self.piazza.user_login(email=self.email, password=self.password)
            self._authenticated = True
            console.print("[green]✓ Successfully logged in to Piazza[/green]")
            return True
        except Exception as e:
            console.print(f"[red]✗ Login failed: {e}[/red]")
            return False
    
    def get_network(self, network_id: str):
        """
        Get a Piazza network (course) by ID.
        
        Args:
            network_id: The network ID (found in Piazza URL)
            
        Returns:
            Network object for the course
        """
        if not self._authenticated:
            raise RuntimeError("Must login before accessing networks")
        
        try:
            network = self.piazza.network(network_id)
            console.print(f"[green]✓ Connected to network: {network_id}[/green]")
            return network
        except Exception as e:
            console.print(f"[red]✗ Failed to access network: {e}[/red]")
            raise
    
    def list_user_classes(self) -> list:
        """
        List all classes the user has access to.
        
        Returns:
            List of class information dictionaries
        """
        if not self._authenticated:
            raise RuntimeError("Must login before listing classes")
        
        try:
            classes = self.piazza.get_user_classes()
            return classes
        except Exception as e:
            console.print(f"[red]✗ Failed to list classes: {e}[/red]")
            return []

