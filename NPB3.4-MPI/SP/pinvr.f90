
!---------------------------------------------------------------------
!---------------------------------------------------------------------

subroutine pinvr(c)

!---------------------------------------------------------------------
!---------------------------------------------------------------------

!---------------------------------------------------------------------
!   block-diagonal matrix-vector multiplication
!---------------------------------------------------------------------

  use sp_data
  implicit none

  integer i, j, k, c
  double precision r1, r2, r3, r4, r5, t1, t2

!---------------------------------------------------------------------
!      treat only one cell
!---------------------------------------------------------------------
  do k = start(3, c), cell_size(3, c) - end(3, c) - 1
    do j = start(2, c), cell_size(2, c) - end(2, c) - 1
      do i = start(1, c), cell_size(1, c) - end(1, c) - 1

        r1 = rhs(i, j, k, 1, c)
        r2 = rhs(i, j, k, 2, c)
        r3 = rhs(i, j, k, 3, c)
        r4 = rhs(i, j, k, 4, c)
        r5 = rhs(i, j, k, 5, c)

        t1 = bt*r1
        t2 = 0.5d0*(r4 + r5)

        rhs(i, j, k, 1, c) = bt*(r4 - r5)
        rhs(i, j, k, 2, c) = -r3
        rhs(i, j, k, 3, c) = r2
        rhs(i, j, k, 4, c) = -t1 + t2
        rhs(i, j, k, 5, c) = t1 + t2
      end do
    end do
  end do

  return
end

