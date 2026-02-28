import { useState } from 'react';
import {
  Modal, ModalVariant, ModalHeader, ModalBody, ModalFooter,
  Button, Form, FormGroup, TextInput,
  Alert as PfAlert,
} from '@patternfly/react-core';
import { useNavigate } from 'react-router-dom';
import { auth } from '../../api/client';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  log: (msg: string, type?: 'info' | 'success' | 'error') => void;
}

export function LoginModal({ isOpen, onClose, log }: Props) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleSubmit = async () => {
    try {
      await auth.login(password);
      log('Admin login successful', 'success');
      setPassword('');
      setError('');
      onClose();
      navigate('/admin');
    } catch (err) {
      setError((err as Error).message || 'Login failed');
    }
  };

  return (
    <Modal
      variant={ModalVariant.small}
      isOpen={isOpen}
      onClose={onClose}
      aria-label="Admin login"
    >
      <ModalHeader title="Admin Login" />
      <ModalBody>
        {error && <PfAlert variant="danger" title={error} isInline style={{ marginBottom: '1rem' }} id="login-error" />}
        <Form onSubmit={e => { e.preventDefault(); handleSubmit(); }} id="login-form">
          <FormGroup label="Password" fieldId="login-password" isRequired>
            <TextInput
              id="login-password"
              type="password"
              value={password}
              onChange={(_e, val) => setPassword(val)}
              placeholder="Enter admin password"
              isRequired
            />
          </FormGroup>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button variant="primary" onClick={handleSubmit}>Login</Button>
      </ModalFooter>
    </Modal>
  );
}
