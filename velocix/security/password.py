"""Password hashing with scrypt and argon2"""
import hashlib
import secrets
import hmac
import base64
import time
from typing import Optional, Literal


class TimingSafeComparison:
    """Timing-safe string comparison to prevent timing attacks"""
    
    @staticmethod
    def compare(a: str, b: str) -> bool:
        """Compare two strings in constant time"""
        return hmac.compare_digest(a.encode('utf-8'), b.encode('utf-8'))
    
    @staticmethod
    def compare_bytes(a: bytes, b: bytes) -> bool:
        """Compare two byte strings in constant time"""
        return hmac.compare_digest(a, b)


class PasswordStrengthValidator:
    """Validate password strength"""
    
    __slots__ = ("_min_length", "_require_uppercase", "_require_lowercase", "_require_digit", "_require_special")
    
    def __init__(
        self,
        min_length: int = 8,
        require_uppercase: bool = True,
        require_lowercase: bool = True,
        require_digit: bool = True,
        require_special: bool = True
    ) -> None:
        self._min_length = min_length
        self._require_uppercase = require_uppercase
        self._require_lowercase = require_lowercase
        self._require_digit = require_digit
        self._require_special = require_special
    
    def validate(self, password: str) -> tuple[bool, list[str]]:
        """Validate password strength, return (is_valid, errors)"""
        errors: list[str] = []
        
        if len(password) < self._min_length:
            errors.append(f"Password must be at least {self._min_length} characters long")
        
        if self._require_uppercase and not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter")
        
        if self._require_lowercase and not any(c.islower() for c in password):
            errors.append("Password must contain at least one lowercase letter")
        
        if self._require_digit and not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one digit")
        
        if self._require_special:
            special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
            if not any(c in special_chars for c in password):
                errors.append("Password must contain at least one special character")
        
        return len(errors) == 0, errors
    
    def estimate_strength(self, password: str) -> Literal["weak", "medium", "strong", "very_strong"]:
        """Estimate password strength"""
        score = 0
        
        if len(password) >= 8:
            score += 1
        if len(password) >= 12:
            score += 1
        if len(password) >= 16:
            score += 1
        
        if any(c.isupper() for c in password):
            score += 1
        if any(c.islower() for c in password):
            score += 1
        if any(c.isdigit() for c in password):
            score += 1
        if any(not c.isalnum() for c in password):
            score += 1
        
        if score <= 2:
            return "weak"
        elif score <= 4:
            return "medium"
        elif score <= 6:
            return "strong"
        else:
            return "very_strong"


class PasswordHasher:
    """Secure password hashing using scrypt with pepper and version support"""
    
    __slots__ = ("_n", "_r", "_p", "_maxmem", "_dklen", "_pepper", "_version", "_validator")
    
    def __init__(
        self,
        n: int = 16384,
        r: int = 8,
        p: int = 1,
        maxmem: int = 67108864,
        dklen: int = 64,
        pepper: Optional[str] = None,
        version: int = 1,
        validator: Optional[PasswordStrengthValidator] = None
    ) -> None:
        self._n = n
        self._r = r
        self._p = p
        self._maxmem = maxmem
        self._dklen = dklen
        self._pepper = pepper.encode('utf-8') if pepper else b''
        self._version = version
        self._validator = validator
    
    def hash_password(self, password: str, validate_strength: bool = True) -> str:
        """Hash password with random salt, pepper, and version"""
        if validate_strength and self._validator:
            is_valid, errors = self._validator.validate(password)
            if not is_valid:
                raise ValueError(f"Password validation failed: {'; '.join(errors)}")
        
        if not password:
            raise ValueError("Password cannot be empty")
        
        salt = secrets.token_bytes(32)
        
        password_with_pepper = password.encode("utf-8") + self._pepper
        
        hash_bytes = hashlib.scrypt(
            password_with_pepper,
            salt=salt,
            n=self._n,
            r=self._r,
            p=self._p,
            maxmem=self._maxmem,
            dklen=self._dklen
        )
        
        version_byte = self._version.to_bytes(1, 'big')
        result = version_byte + salt + hash_bytes
        
        return base64.b64encode(result).decode('ascii')
    
    def verify_password(self, password: str, password_hash: str, constant_time: bool = True) -> bool:
        """Verify password against hash with timing attack protection"""
        try:
            if constant_time:
                start_time = time.perf_counter()
            
            decoded = base64.b64decode(password_hash.encode('ascii'))
            
            if len(decoded) < 33:
                decoded_old = bytes.fromhex(password_hash)
                salt = decoded_old[:32]
                stored_hash = decoded_old[32:]
                version = 0
            else:
                version = int.from_bytes(decoded[0:1], 'big')
                salt = decoded[1:33]
                stored_hash = decoded[33:]
            
            password_with_pepper = password.encode("utf-8") + self._pepper
            
            new_hash = hashlib.scrypt(
                password_with_pepper,
                salt=salt,
                n=self._n,
                r=self._r,
                p=self._p,
                maxmem=self._maxmem,
                dklen=self._dklen
            )
            
            result = hmac.compare_digest(stored_hash, new_hash)
            
            if constant_time:
                elapsed = time.perf_counter() - start_time
                min_time = 0.001
                if elapsed < min_time:
                    time.sleep(min_time - elapsed)
            
            return result
        
        except Exception:
            if constant_time:
                time.sleep(0.001)
            return False
    
    def generate_random_password(
        self, 
        length: int = 16,
        use_uppercase: bool = True,
        use_lowercase: bool = True,
        use_digits: bool = True,
        use_special: bool = True
    ) -> str:
        """Generate secure random password with character requirements"""
        if length < 4:
            raise ValueError("Password length must be at least 4")
        
        chars = ""
        required_chars: list[str] = []
        
        if use_lowercase:
            lowercase = "abcdefghijklmnopqrstuvwxyz"
            chars += lowercase
            required_chars.append(secrets.choice(lowercase))
        
        if use_uppercase:
            uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            chars += uppercase
            required_chars.append(secrets.choice(uppercase))
        
        if use_digits:
            digits = "0123456789"
            chars += digits
            required_chars.append(secrets.choice(digits))
        
        if use_special:
            special = "!@#$%^&*()_+-=[]{}|;:,.<>?"
            chars += special
            required_chars.append(secrets.choice(special))
        
        if not chars:
            raise ValueError("At least one character type must be enabled")
        
        remaining_length = length - len(required_chars)
        random_chars = [secrets.choice(chars) for _ in range(remaining_length)]
        
        all_chars = required_chars + random_chars
        secrets.SystemRandom().shuffle(all_chars)
        
        return ''.join(all_chars)
    
    def needs_rehash(self, password_hash: str) -> bool:
        """Check if hash needs to be updated (version changed)"""
        try:
            decoded = base64.b64decode(password_hash.encode('ascii'))
            if len(decoded) < 33:
                return True
            
            version = int.from_bytes(decoded[0:1], 'big')
            return version != self._version
        except Exception:
            return True


class Argon2Hasher:
    """Argon2 password hasher (requires argon2-cffi)"""
    
    __slots__ = ("_hasher", "_time_cost", "_memory_cost", "_parallelism")
    
    def __init__(
        self,
        time_cost: int = 2,
        memory_cost: int = 65536,
        parallelism: int = 4
    ) -> None:
        try:
            from argon2 import PasswordHasher as Argon2PasswordHasher
            self._hasher = Argon2PasswordHasher(
                time_cost=time_cost,
                memory_cost=memory_cost,
                parallelism=parallelism
            )
        except ImportError:
            raise ImportError("argon2-cffi is required for Argon2Hasher. Install with: pip install argon2-cffi")
        
        self._time_cost = time_cost
        self._memory_cost = memory_cost
        self._parallelism = parallelism
    
    def hash_password(self, password: str) -> str:
        """Hash password with Argon2"""
        return self._hasher.hash(password)
    
    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against Argon2 hash"""
        try:
            self._hasher.verify(password_hash, password)
            return True
        except Exception:
            return False
    
    def needs_rehash(self, password_hash: str) -> bool:
        """Check if hash needs to be updated"""
        return self._hasher.check_needs_rehash(password_hash)


# Alias for compatibility
PasswordManager = PasswordHasher
