class Station < ApplicationRecord
    has_many :ping_results, dependent: :destroy
end
