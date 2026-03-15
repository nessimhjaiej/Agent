import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { X, User, Phone, Mail, Lock, CheckCircle } from 'lucide-react';
import { isPasswordStrong, PASSWORD_POLICY_MESSAGE } from '../utils/passwordPolicy';

export default function ProfileModal({
  isOpen,
  onClose,
  onSubmit,
  user,
  requirePassword = false,
  lockUntilComplete = false,
}) {
  const [username, setUsername] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [profilePictureFile, setProfilePictureFile] = useState(null);
  const [profilePicturePreview, setProfilePicturePreview] = useState('');
  const [removeProfilePicture, setRemoveProfilePicture] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (!isOpen) return;
    setUsername(user?.user_metadata?.username || '');
    setPhoneNumber(user?.user_metadata?.phone_number || '');
    setProfilePictureFile(null);
    setProfilePicturePreview(user?.user_metadata?.profile_picture || '');
    setRemoveProfilePicture(false);
    setNewPassword('');
    setError('');
    setSuccess('');
    setLoading(false);
  }, [isOpen, user]);

  useEffect(() => {
    if (!profilePictureFile) return undefined;
    const preview = URL.createObjectURL(profilePictureFile);
    setProfilePicturePreview(preview);
    return () => URL.revokeObjectURL(preview);
  }, [profilePictureFile]);

  const handleClose = () => {
    if (lockUntilComplete) return;
    onClose();
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setSuccess('');

    if (!lockUntilComplete && !username.trim()) {
      setError('Username is required.');
      return;
    }
    if ((requirePassword || newPassword.trim()) && !isPasswordStrong(newPassword.trim())) {
      setError(PASSWORD_POLICY_MESSAGE);
      return;
    }

    setLoading(true);
    try {
      await onSubmit({
        username: username.trim(),
        phoneNumber: phoneNumber.trim(),
        profilePictureFile,
        removeProfilePicture,
        newPassword: newPassword.trim(),
      });
      setSuccess('Profile updated successfully.');
      if (!lockUntilComplete) {
        onClose();
      }
    } catch (submitError) {
      setError(submitError?.message || 'Failed to update profile.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-md"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={handleClose}
          />

          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
          >
            <div
              className="relative w-full max-w-2xl rounded-2xl"
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                boxShadow: '0 24px 60px rgba(0,0,0,0.4)',
                padding: '30px',
              }}
              onClick={(event) => event.stopPropagation()}
            >
              {!lockUntilComplete && (
                <button
                  type="button"
                  onClick={handleClose}
                  className="absolute top-4 right-4 p-2.5 rounded-lg transition-colors hover:bg-primary-500/10"
                  style={{ color: 'var(--text-muted)' }}
                  aria-label="Close profile dialog"
                >
                  <X size={18} />
                </button>
              )}

              <div className="mb-7">
                <h3 className="text-xl font-semibold font-display" style={{ color: 'var(--text-primary)' }}>
                  {lockUntilComplete ? 'Complete Your Account' : 'Edit Profile'}
                </h3>
                <p className="text-sm mt-2" style={{ color: 'var(--text-secondary)' }}>
                  {lockUntilComplete
                    ? 'To continue, set your password. You can edit other profile info later.'
                    : 'You can update your profile info here. Email cannot be changed.'}
                </p>
              </div>

              <form
                onSubmit={handleSubmit}
                className="flex flex-col gap-3"
                style={{ marginTop: lockUntilComplete ? '14px' : '16px' }}
              >
                {!lockUntilComplete && (
                  <>
                    <div className="rounded-xl" style={{ border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)', padding: '14px 16px' }}>
                      <div className="flex items-center gap-4">
                        <div
                          className="w-16 h-16 rounded-full overflow-hidden flex items-center justify-center shrink-0"
                          style={{
                            border: '1px solid var(--border-color)',
                            background: 'rgba(139,92,246,0.08)',
                            cursor: 'pointer',
                          }}
                          onClick={() => fileInputRef.current?.click()}
                          title="Upload profile picture"
                        >
                          {profilePicturePreview ? (
                            <img src={profilePicturePreview} alt="Profile preview" className="w-full h-full object-cover" />
                          ) : (
                            <User size={26} style={{ color: 'var(--text-muted)' }} />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                            Profile picture
                          </p>
                          <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                            Upload a new photo or remove the current one.
                          </p>
                          <div className="flex items-center gap-2 mt-3">
                            <button
                              type="button"
                              onClick={() => fileInputRef.current?.click()}
                              className="rounded-lg text-xs font-medium"
                              style={{
                                minHeight: '34px',
                                border: '1px solid var(--border-color)',
                                color: 'var(--text-primary)',
                                paddingLeft: '14px',
                                paddingRight: '14px',
                                background: 'var(--bg-secondary)',
                              }}
                            >
                              Upload
                            </button>
                            {profilePicturePreview && (
                              <button
                                type="button"
                                onClick={() => {
                                  setProfilePictureFile(null);
                                  setProfilePicturePreview('');
                                  setRemoveProfilePicture(true);
                                }}
                                className="rounded-lg text-xs font-medium"
                                style={{
                                  minHeight: '34px',
                                  border: '1px solid rgba(239,68,68,0.2)',
                                  color: '#ef4444',
                                  paddingLeft: '14px',
                                  paddingRight: '14px',
                                  background: 'rgba(239,68,68,0.08)',
                                }}
                              >
                                Delete photo
                              </button>
                            )}
                          </div>
                          {profilePictureFile && (
                            <p className="text-xs mt-2 truncate" style={{ color: 'var(--text-muted)' }}>
                              Selected: {profilePictureFile.name}
                            </p>
                          )}
                        </div>
                      </div>
                      <input
                        ref={fileInputRef}
                        id="profile-picture-file"
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={(event) => {
                          const selected = event.target.files?.[0] || null;
                          setProfilePictureFile(selected);
                          if (selected) {
                            setRemoveProfilePicture(false);
                          }
                        }}
                      />
                    </div>

                    <div className="flex items-center gap-3 rounded-xl" style={{ border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)', minHeight: '52px', paddingLeft: '16px', paddingRight: '16px' }}>
                      <User size={16} style={{ color: 'var(--text-muted)' }} />
                      <input id="profile-username" type="text" placeholder="Username (required)" value={username} onChange={(event) => setUsername(event.target.value)} className="flex-1 bg-transparent outline-none text-sm" style={{ color: 'var(--text-primary)' }} required />
                    </div>

                    <div className="flex items-center gap-3 rounded-xl" style={{ border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)', minHeight: '52px', paddingLeft: '16px', paddingRight: '16px' }}>
                      <Mail size={16} style={{ color: 'var(--text-muted)' }} />
                      <input id="profile-email" type="email" value={user?.email || ''} readOnly disabled className="flex-1 bg-transparent outline-none text-sm" style={{ color: 'var(--text-muted)' }} />
                    </div>

                    <div className="flex items-center gap-3 rounded-xl" style={{ border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)', minHeight: '52px', paddingLeft: '16px', paddingRight: '16px' }}>
                      <Phone size={16} style={{ color: 'var(--text-muted)' }} />
                      <input id="profile-phone" type="tel" placeholder="Phone number (optional)" value={phoneNumber} onChange={(event) => setPhoneNumber(event.target.value)} className="flex-1 bg-transparent outline-none text-sm" style={{ color: 'var(--text-primary)' }} />
                    </div>
                  </>
                )}

                {(requirePassword || lockUntilComplete) && (
                  <>
                    <div className="flex items-center gap-3 rounded-xl" style={{ border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)', minHeight: '52px', paddingLeft: '16px', paddingRight: '16px' }}>
                      <Lock size={16} style={{ color: 'var(--text-muted)' }} />
                      <input id="profile-password" type="password" placeholder={lockUntilComplete ? 'Set password (required)' : 'New password (optional)'} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} minLength={8} required={requirePassword} className="flex-1 bg-transparent outline-none text-sm" style={{ color: 'var(--text-primary)' }} />
                    </div>
                    <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                      Password must be at least 8 characters and include uppercase, lowercase, number, and special character.
                    </p>
                  </>
                )}

                {error && (
                  <p className="text-sm rounded-lg" style={{ background: 'rgba(239,68,68,0.08)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.2)', padding: '10px 12px' }}>
                    {error}
                  </p>
                )}

                {success && (
                  <p className="text-sm rounded-lg flex items-center gap-2" style={{ background: 'rgba(16,185,129,0.1)', color: '#10b981', border: '1px solid rgba(16,185,129,0.2)', padding: '10px 12px' }}>
                    <CheckCircle size={14} />
                    {success}
                  </p>
                )}

                <div className="flex items-center justify-end gap-3 mt-2">
                  {!lockUntilComplete && (
                    <button
                      type="button"
                      onClick={handleClose}
                      className="rounded-xl text-sm font-medium"
                      style={{
                        color: 'var(--text-secondary)',
                        border: '1px solid var(--border-color)',
                        minHeight: '44px',
                        minWidth: '130px',
                        paddingLeft: '24px',
                        paddingRight: '24px',
                      }}
                    >
                      Cancel
                    </button>
                  )}
                  <button
                    id="profile-save-btn"
                    type="submit"
                    disabled={loading}
                    className="rounded-xl text-sm font-semibold text-white disabled:opacity-60"
                    style={{
                      background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
                      minHeight: '44px',
                      minWidth: lockUntilComplete ? '160px' : '130px',
                      paddingLeft: lockUntilComplete ? '24px' : '24px',
                      paddingRight: lockUntilComplete ? '24px' : '24px',
                    }}
                  >
                    {loading ? 'Saving...' : 'Save'}
                  </button>
                </div>
              </form>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
