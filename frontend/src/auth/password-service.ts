import { updatePassword } from "aws-amplify/auth";

export async function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  await updatePassword({
    oldPassword,
    newPassword,
  });
}
