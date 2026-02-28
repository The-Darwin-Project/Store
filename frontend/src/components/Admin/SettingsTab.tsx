import { useState } from 'react';
import {
  Button, Form, FormGroup, TextInput,
  Alert as PfAlert,
} from '@patternfly/react-core';
import { auth } from '../../api/client';

interface Props {
  log: (msg: string, type?: 'info' | 'success' | 'error') => void;
}

export function SettingsTab({ log }: Props) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [message, setMessage] = useState<{ text: string; variant: 'success' | 'danger' } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      setMessage({ text: 'Passwords do not match', variant: 'danger' });
      return;
    }
    if (newPassword.length < 8) {
      setMessage({ text: 'Password must be at least 8 characters', variant: 'danger' });
      return;
    }
    try {
      await auth.changePassword(currentPassword, newPassword);
      setMessage({ text: 'Password changed successfully', variant: 'success' });
      log('Password changed successfully', 'success');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (error) {
      const msg = (error as Error).message || 'Failed to change password';
      setMessage({ text: msg, variant: 'danger' });
      log(`Failed to change password: ${msg}`, 'error');
    }
  };

  return (
    <div id="settings">
      <div className="ds-panel">
        <h2>Change Admin Password</h2>
        <Form onSubmit={handleSubmit} id="change-password-form" style={{ maxWidth: '400px' }}>
          <FormGroup label="Current Password" fieldId="current-password" isRequired>
            <TextInput id="current-password" type="password" value={currentPassword}
              onChange={(_e, v) => setCurrentPassword(v)} isRequired placeholder="Enter current password" />
          </FormGroup>
          <FormGroup label="New Password" fieldId="new-password" isRequired>
            <TextInput id="new-password" type="password" value={newPassword}
              onChange={(_e, v) => setNewPassword(v)} isRequired placeholder="Enter new password (min 8 chars)" />
          </FormGroup>
          <FormGroup label="Confirm New Password" fieldId="confirm-password" isRequired>
            <TextInput id="confirm-password" type="password" value={confirmPassword}
              onChange={(_e, v) => setConfirmPassword(v)} isRequired placeholder="Confirm new password" />
          </FormGroup>
          {message && (
            <div id="password-change-msg" style={{ marginTop: '1rem' }}>
              <PfAlert variant={message.variant} title={message.text} isInline />
            </div>
          )}
          <Button type="submit" variant="primary" style={{ marginTop: '1rem' }}>Change Password</Button>
        </Form>
      </div>
    </div>
  );
}
