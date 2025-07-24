class Station < ApplicationRecord
  has_many :ping_results, dependent: :destroy
  has_many :readings, dependent: :destroy

  validates :name, :ip_address, presence: true
  validates :ip_address, uniqueness: true
end
