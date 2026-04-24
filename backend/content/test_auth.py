"""Tests for authentication endpoints."""
import json
from django.test import TestCase, Client
from django.urls import reverse
from content.models import User
from content.auth import hash_password, verify_password


class AuthenticationTestCase(TestCase):
	"""Test cases for authentication functionality."""

	def setUp(self):
		"""Set up test fixtures."""
		self.client = Client()
		self.register_url = '/api/auth/register'
		self.login_url = '/api/auth/login'
		self.refresh_url = '/api/auth/refresh'
		self.me_url = '/api/auth/me'
		self.update_url = '/api/auth/me/update'
		self.change_password_url = '/api/auth/change-password'

		# Test user data
		self.test_user_data = {
			'username': 'testuser',
			'email': 'test@example.com',
			'password': 'TestPassword123',
			'first_name': 'Test',
			'last_name': 'User',
			'profile': 'Student',
		}

	def test_user_registration_success(self):
		"""Test successful user registration."""
		response = self.client.post(
			self.register_url,
			data=json.dumps(self.test_user_data),
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 201)
		data = json.loads(response.content)

		self.assertIn('user', data)
		self.assertIn('tokens', data)
		self.assertEqual(data['user']['username'], 'testuser')
		self.assertEqual(data['user']['email'], 'test@example.com')
		self.assertEqual(data['user']['profile'], 'Student')

		# Verify token structure
		self.assertIn('access_token', data['tokens'])
		self.assertIn('refresh_token', data['tokens'])
		self.assertEqual(data['tokens']['token_type'], 'Bearer')

	def test_registration_username_too_short(self):
		"""Test registration with username too short."""
		data = self.test_user_data.copy()
		data['username'] = 'ab'

		response = self.client.post(
			self.register_url,
			data=json.dumps(data),
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 400)
		self.assertIn('at least 3 characters', response.content.decode())

	def test_registration_password_too_short(self):
		"""Test registration with password too short."""
		data = self.test_user_data.copy()
		data['password'] = 'short'

		response = self.client.post(
			self.register_url,
			data=json.dumps(data),
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 400)
		self.assertIn('at least 8 characters', response.content.decode())

	def test_registration_invalid_email(self):
		"""Test registration with invalid email."""
		data = self.test_user_data.copy()
		data['email'] = 'invalid-email'

		response = self.client.post(
			self.register_url,
			data=json.dumps(data),
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 400)
		self.assertIn('Invalid email', response.content.decode())

	def test_registration_duplicate_username(self):
		"""Test registration with duplicate username."""
		# Create first user
		User.objects.create(
			username='testuser',
			email='user1@example.com',
			password_hash=hash_password('Password123'),
		)

		# Try to register with same username
		response = self.client.post(
			self.register_url,
			data=json.dumps(self.test_user_data),
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 409)
		self.assertIn('already exists', response.content.decode())

	def test_login_success(self):
		"""Test successful login."""
		# Create user
		User.objects.create(
			username='testuser',
			email='test@example.com',
			password_hash=hash_password('TestPassword123'),
			first_name='Test',
			last_name='User',
			profile='Student',
		)

		response = self.client.post(
			self.login_url,
			data=json.dumps({
				'username': 'testuser',
				'password': 'TestPassword123',
			}),
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 200)
		data = json.loads(response.content)

		self.assertIn('user', data)
		self.assertIn('tokens', data)
		self.assertEqual(data['user']['username'], 'testuser')

	def test_login_invalid_credentials(self):
		"""Test login with invalid credentials."""
		# Create user
		User.objects.create(
			username='testuser',
			email='test@example.com',
			password_hash=hash_password('TestPassword123'),
		)

		response = self.client.post(
			self.login_url,
			data=json.dumps({
				'username': 'testuser',
				'password': 'WrongPassword',
			}),
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 401)
		self.assertIn('Invalid credentials', response.content.decode())

	def test_get_current_user(self):
		"""Test getting current user info."""
		# Create user
		user = User.objects.create(
			username='testuser',
			email='test@example.com',
			password_hash=hash_password('TestPassword123'),
			first_name='Test',
			last_name='User',
			profile='Student',
		)

		# Get tokens
		login_response = self.client.post(
			self.login_url,
			data=json.dumps({
				'username': 'testuser',
				'password': 'TestPassword123',
			}),
			content_type='application/json',
		)

		tokens = json.loads(login_response.content)['tokens']
		access_token = tokens['access_token']

		# Get current user
		response = self.client.get(
			self.me_url,
			HTTP_AUTHORIZATION=f'Bearer {access_token}',
		)

		self.assertEqual(response.status_code, 200)
		data = json.loads(response.content)

		self.assertEqual(data['user']['username'], 'testuser')
		self.assertEqual(data['user']['email'], 'test@example.com')

	def test_update_user_profile(self):
		"""Test updating user profile."""
		# Create user
		user = User.objects.create(
			username='testuser',
			email='test@example.com',
			password_hash=hash_password('TestPassword123'),
			first_name='Test',
			last_name='User',
			profile='Student',
		)

		# Get token
		login_response = self.client.post(
			self.login_url,
			data=json.dumps({
				'username': 'testuser',
				'password': 'TestPassword123',
			}),
			content_type='application/json',
		)

		tokens = json.loads(login_response.content)['tokens']
		access_token = tokens['access_token']

		# Update profile
		response = self.client.patch(
			self.update_url,
			data=json.dumps({
				'first_name': 'Updated',
				'profile': 'Academic staff',
			}),
			content_type='application/json',
			HTTP_AUTHORIZATION=f'Bearer {access_token}',
		)

		self.assertEqual(response.status_code, 200)
		data = json.loads(response.content)

		self.assertEqual(data['user']['first_name'], 'Updated')
		self.assertEqual(data['user']['profile'], 'Academic staff')

	def test_change_password_success(self):
		"""Test successful password change."""
		# Create user
		user = User.objects.create(
			username='testuser',
			email='test@example.com',
			password_hash=hash_password('OldPassword123'),
		)

		# Get token
		login_response = self.client.post(
			self.login_url,
			data=json.dumps({
				'username': 'testuser',
				'password': 'OldPassword123',
			}),
			content_type='application/json',
		)

		tokens = json.loads(login_response.content)['tokens']
		access_token = tokens['access_token']

		# Change password
		response = self.client.post(
			self.change_password_url,
			data=json.dumps({
				'old_password': 'OldPassword123',
				'new_password': 'NewPassword456',
			}),
			content_type='application/json',
			HTTP_AUTHORIZATION=f'Bearer {access_token}',
		)

		self.assertEqual(response.status_code, 200)

		# Verify old password doesn't work
		login_response = self.client.post(
			self.login_url,
			data=json.dumps({
				'username': 'testuser',
				'password': 'OldPassword123',
			}),
			content_type='application/json',
		)

		self.assertEqual(login_response.status_code, 401)

		# Verify new password works
		login_response = self.client.post(
			self.login_url,
			data=json.dumps({
				'username': 'testuser',
				'password': 'NewPassword456',
			}),
			content_type='application/json',
		)

		self.assertEqual(login_response.status_code, 200)


class PasswordHashingTestCase(TestCase):
	"""Test password hashing and verification."""

	def test_password_hashing(self):
		"""Test password hashing."""
		password = 'TestPassword123'
		hashed = hash_password(password)

		# Should have two parts (salt and hash)
		self.assertIn('$', hashed)
		parts = hashed.split('$')
		self.assertEqual(len(parts), 2)

	def test_password_verification_success(self):
		"""Test successful password verification."""
		password = 'TestPassword123'
		hashed = hash_password(password)

		self.assertTrue(verify_password(password, hashed))

	def test_password_verification_failure(self):
		"""Test failed password verification."""
		password = 'TestPassword123'
		hashed = hash_password(password)

		self.assertFalse(verify_password('WrongPassword', hashed))

	def test_different_salts(self):
		"""Test that same password with different salts produces different hashes."""
		password = 'TestPassword123'
		hash1 = hash_password(password)
		hash2 = hash_password(password)

		# Hashes should be different due to different salts
		self.assertNotEqual(hash1, hash2)

		# But both should verify the same password
		self.assertTrue(verify_password(password, hash1))
		self.assertTrue(verify_password(password, hash2))
