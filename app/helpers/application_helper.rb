# File: app/helpers/application_helper.rb
# Path: /app/helpers/application_helper.rb
module ApplicationHelper
  # Returns a displayable user name without depending on Devise or any auth.
  def safe_current_user_name
    if defined?(current_user) && current_user && current_user.respond_to?(:name)
      current_user.name
    else
      ENV["USERNAME"] || ENV["USER"] || "user"
    end
  end
end
