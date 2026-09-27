
export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[]

export type Database = {
  
  "api": {
          Tables: {
            [_ in never]: never
          }
          Views: {
            "events_public": {
                  Row: {
                    "application_deadline": string | null,"application_url": string | null,"banner_url": string | null,"categories": (string)[] | null,"city": string | null,"country": string | null,"currency": string | null,"description": string | null,"eligibility": string | null,"end_date": string | null,"format": "in_person"|"online"|"hybrid" | null,"id": string | null,"is_free": boolean | null,"official_url": string | null,"organizer": string | null,"organizer_logo_url": string | null,"poster_url": string | null,"prize_pool": number | null,"published_at": string | null,"slug": string | null,"start_date": string | null,"summary": string | null,"team_max": number | null,"team_min": number | null,"technologies": (string)[] | null,"timezone": string | null,"title": string | null,"updated_at": string | null,"venue": string | null,"verification_status": "unverified"|"partially_verified"|"verified" | null
                  }
                  Insert: {
                           "application_deadline"?: string | null,"application_url"?: string | null,"banner_url"?: string | null,"categories"?: (string)[] | null,"city"?: string | null,"country"?: string | null,"currency"?: string | null,"description"?: string | null,"eligibility"?: string | null,"end_date"?: string | null,"format"?: "in_person"|"online"|"hybrid" | null,"id"?: string | null,"is_free"?: boolean | null,"official_url"?: string | null,"organizer"?: string | null,"organizer_logo_url"?: string | null,"poster_url"?: string | null,"prize_pool"?: number | null,"published_at"?: string | null,"slug"?: string | null,"start_date"?: string | null,"summary"?: string | null,"team_max"?: number | null,"team_min"?: number | null,"technologies"?: (string)[] | null,"timezone"?: string | null,"title"?: string | null,"updated_at"?: string | null,"venue"?: string | null,"verification_status"?: "unverified"|"partially_verified"|"verified" | null
                         }
                        Update: {
                           "application_deadline"?: string | null,"application_url"?: string | null,"banner_url"?: string | null,"categories"?: (string)[] | null,"city"?: string | null,"country"?: string | null,"currency"?: string | null,"description"?: string | null,"eligibility"?: string | null,"end_date"?: string | null,"format"?: "in_person"|"online"|"hybrid" | null,"id"?: string | null,"is_free"?: boolean | null,"official_url"?: string | null,"organizer"?: string | null,"organizer_logo_url"?: string | null,"poster_url"?: string | null,"prize_pool"?: number | null,"published_at"?: string | null,"slug"?: string | null,"start_date"?: string | null,"summary"?: string | null,"team_max"?: number | null,"team_min"?: number | null,"technologies"?: (string)[] | null,"timezone"?: string | null,"title"?: string | null,"updated_at"?: string | null,"venue"?: string | null,"verification_status"?: "unverified"|"partially_verified"|"verified" | null
                         }
                        Relationships: [
                    
                  ]
                }
          }
          Functions: {
            "keep_alive":
{ Args: { "source": string }; Returns: number
                           },
"submit_community_application":
{ Args: { "payload": Json }; Returns: undefined
                           },
"submit_team_application":
{ Args: { "payload": Json }; Returns: undefined
                           }
          }
          Enums: {
            [_ in never]: never
          }
          CompositeTypes: {
            [_ in never]: never
          }
        }
}

type DatabaseWithoutInternals = Omit<Database, '__InternalSupabase'>

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never
> = DefaultSchemaTableNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
  ? (DefaultSchema["Tables"] & DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
      Row: infer R
    }
    ? R
    : never
  : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never
> = DefaultSchemaTableNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
  ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
      Insert: infer I
    }
    ? I
    : never
  : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never
> = DefaultSchemaTableNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
  ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
      Update: infer U
    }
    ? U
    : never
  : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never
> = DefaultSchemaEnumNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
  ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
  : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never
> = PublicCompositeTypeNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
  ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
  : never

export const Constants = {
  "api": {
          Enums: {
            
          }
        }
} as const

