"""
Piazza authentication module with SSO support.
"""
import json
import requests
from pathlib import Path
from piazza_api import Piazza
from piazza_api.network import Network
from rich.console import Console

console = Console()


class PiazzaAuth:
    """Handles Piazza authentication and network access."""
    
    def __init__(self, email: str = None, password: str = None):
        """
        Initialize Piazza authentication.
        
        Args:
            email: Piazza account email (optional if using cookies)
            password: Piazza account password (optional if using cookies)
        """
        self.email = email
        self.password = password
        self.piazza = Piazza()
        self._authenticated = False
        self._session = None
    
    def login(self) -> bool:
        """
        Authenticate with Piazza using email/password.
        
        Returns:
            True if authentication successful, False otherwise
        """
        try:
            console.print(f"[yellow]Logging in as {self.email}...[/yellow]")
            self.piazza.user_login(email=self.email, password=self.password)
            self._authenticated = True
            self._session = self.piazza._rpc.session
            console.print("[green]✓ Successfully logged in to Piazza[/green]")
            return True
        except Exception as e:
            console.print(f"[red]✗ Login failed: {e}[/red]")
            console.print("[yellow]If your institution uses SSO, try using cookie-based auth.[/yellow]")
            return False
    
    def login_with_cookies(self, cookies: dict) -> bool:
        """
        Authenticate using session cookies from browser.
        
        This is useful for SSO-based institutions where standard login doesn't work.
        
        Args:
            cookies: Dictionary of cookies from authenticated browser session
            
        Returns:
            True if authentication successful, False otherwise
        """
        try:
            console.print("[yellow]Authenticating with cookies...[/yellow]")
            
            # Create a session with the provided cookies
            session = requests.Session()
            for name, value in cookies.items():
                session.cookies.set(name, value, domain='.piazza.com')
            
            # Test the session by fetching user profile
            response = session.get('https://piazza.com/logic/api?method=user.status')
            
            if response.status_code == 200:
                data = response.json()
                if data.get('result'):
                    # Inject the session into piazza-api
                    self.piazza._rpc.session = session
                    self._session = session
                    self._authenticated = True
                    
                    user_info = data.get('result', {})
                    console.print(f"[green]✓ Authenticated as: {user_info.get('email', 'Unknown')}[/green]")
                    return True
            
            console.print("[red]✗ Cookie authentication failed - cookies may be expired[/red]")
            return False
            
        except Exception as e:
            console.print(f"[red]✗ Cookie auth failed: {e}[/red]")
            return False
    
    def login_with_cookie_file(self, cookie_file: Path) -> bool:
        """
        Load cookies from a JSON file and authenticate.
        
        Args:
            cookie_file: Path to JSON file containing cookies
            
        Returns:
            True if authentication successful
        """
        try:
            with open(cookie_file, 'r') as f:
                cookies = json.load(f)
            return self.login_with_cookies(cookies)
        except FileNotFoundError:
            console.print(f"[red]✗ Cookie file not found: {cookie_file}[/red]")
            return False
        except json.JSONDecodeError:
            console.print(f"[red]✗ Invalid JSON in cookie file[/red]")
            return False
    
    def save_cookies(self, cookie_file: Path):
        """
        Save current session cookies to a file.
        
        Args:
            cookie_file: Path to save cookies
        """
        if self._session:
            cookies = {c.name: c.value for c in self._session.cookies}
            with open(cookie_file, 'w') as f:
                json.dump(cookies, f, indent=2)
            console.print(f"[green]✓ Cookies saved to {cookie_file}[/green]")
    
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
    
    def get_network_with_session(self, network_id: str):
        """
        Get a network using the raw session (for SSO auth).
        
        Args:
            network_id: The network ID
            
        Returns:
            Custom network accessor
        """
        if not self._authenticated or not self._session:
            raise RuntimeError("Must login before accessing networks")
        
        return NetworkAccessor(self._session, network_id)
    
    def list_user_classes(self) -> list:
        """
        List all classes the user has access to.
        
        Returns:
            List of class information dictionaries
        """
        if not self._authenticated:
            raise RuntimeError("Must login before listing classes")
        
        try:
            # Try the standard method first
            if hasattr(self.piazza, 'get_user_classes'):
                classes = self.piazza.get_user_classes()
                return classes
        except:
            pass
        
        # Fallback: use raw session
        if self._session:
            try:
                response = self._session.get(
                    'https://piazza.com/logic/api?method=user.status'
                )
                data = response.json()
                if data.get('result'):
                    return data['result'].get('networks', [])
            except Exception as e:
                console.print(f"[red]✗ Failed to list classes: {e}[/red]")
        
        return []


class NetworkAccessor:
    """
    Custom network accessor that works with raw session cookies.
    Used when SSO authentication is required.
    """
    
    def __init__(self, session: requests.Session, network_id: str):
        self.session = session
        self.network_id = network_id
        self.base_url = 'https://piazza.com/logic/api'
    
    def _api_call(self, method: str, params: dict = None) -> dict:
        """Make an API call to Piazza."""
        payload = {
            'method': method,
            'params': params or {}
        }
        
        response = self.session.post(
            self.base_url,
            data={'method': method, 'params': json.dumps(params or {})}
        )
        
        return response.json()
    
    def get_feed(self, limit: int = 999999) -> dict:
        """Get the feed of posts."""
        result = self._api_call('network.get_my_feed', {
            'nid': self.network_id,
            'limit': limit,
            'offset': 0
        })
        return result.get('result', {})
    
    def get_post(self, cid: str) -> dict:
        """Get a single post by ID."""
        result = self._api_call('content.get', {
            'nid': self.network_id,
            'cid': cid
        })
        return result.get('result', {})
    
    def iter_all_posts(self, limit: int = None):
        """Iterate through all posts."""
        feed = self.get_feed(limit=limit or 999999)
        feed_items = feed.get('feed', [])
        
        if limit:
            feed_items = feed_items[:limit]
        
        for item in feed_items:
            cid = item.get('id')
            if cid:
                post = self.get_post(cid)
                if post:
                    yield post
